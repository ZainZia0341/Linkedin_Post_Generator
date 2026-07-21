from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import random
import re
from threading import Lock
import time
from typing import Any, Callable
from uuid import uuid4
import zipfile
from xml.etree import ElementTree

from app.api.schemas import (
    ActivityResponse,
    BrainstormRequest,
    BrainstormResponse,
    BulkCreatorImportResponse,
    BulkCreatorPreviewResponse,
    CommentResponse,
    CommentedActivityResponse,
    CreatorProfileDetailsResponse,
    CreatorResponse,
    DashboardStatsResponse,
    DeleteResponse,
    CommentReplyActionRequest,
    ConnectionRequestActionRequest,
    DmActionRequest,
    GenerateCommentRequest,
    GenerateFromActivityRequest,
    GeneratePostRequest,
    LinkedInActionBatchResponse,
    LinkedInActionLogResponse,
    LinkedInActionResult,
    LinkedInPostPublishRequest,
    LinkedInPostPublishResponse,
    LinkedInProspectResponse,
    MarkCommentedRequest,
    ModifyCommentRequest,
    ModifyPostRequest,
    OwnPostResponse,
    PostEngagementScrapeResponse,
    PostEngagerResponse,
    RecentActivitiesResponse,
    RecentScrapeCreatorsRequest,
    RecentScrapeCreatorsResponse,
    ScrapePostEngagementRequest,
    ScrapeCreatorProfilesRequest,
    ScrapeCreatorProfilesResponse,
    ScrapeCreatorsRequest,
    ScrapeCreatorsResponse,
    ScrapeJobStartResponse,
    ScrapeJobStatusResponse,
    SyncRecentOwnPostsRequest,
    SyncRecentOwnPostsResponse,
    ThreadResponse,
    ThreadSummary,
    UserResponse,
)
from app.config import (
    API_LIST_LIMIT,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    LINKEDIN_AUTOMATION_MODE,
    MAX_REVIEW_ATTEMPTS,
    PROVIDER_MODELS,
    SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS,
    SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS,
    SCRAPE_MAX_WORKERS,
)
from app.creator_tracking import get_profile_id, normalize_linkedin_profile_url
from app.db.dynamodb import DynamoRepository
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.linkedin_post_actions import reply_to_comment, send_connection_request, send_dm
from app.linkedin_post_engagement import scrape_linkedin_post_engagement
from app.linkedin_playwright_scraper import fetch_profile_details, fetch_recent_profile_posts
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import GeneratedComment
from app.llms.prompts import (
    COMMENT_GENERATION_SYSTEM_PROMPT,
    COMMENT_GENERATION_USER_PROMPT,
    COMMENT_MODIFICATION_SYSTEM_PROMPT,
    COMMENT_MODIFICATION_USER_PROMPT,
)
from app.post_generation_styles import (
    generation_style_labels,
    generation_style_prompt,
    normalize_generation_style,
)
from app.post_formatting import HASHTAG_RE, format_linkedin_post
from app.writing_style_extract import extract_writing_style, get_builtin_writing_style

POST_CREATION_ACTIONS = generation_style_labels()
COMMENT_TOPICS = ["Add Value", "Congratulate", "Agree", "Disagree", "Challenge", "Expert Insight"]
LINKEDIN_URL_RE = re.compile(r"(?<![a-z0-9.-])(?:https?://)?(?:www\.)?linkedin\.com(?:/[^\s<>'\"]*)?", flags=re.I)
LINKEDIN_ACTIVITY_RE = re.compile(r"urn:li:activity:\d+", flags=re.I)
CREATOR_IMPORT_EXISTING_LIMIT = 1000
RECENTLY_ADDED_WINDOW_DAYS = 1
SCRAPING_STALE_AFTER_HOURS = 24
RECENT_ACTIVITY_RETENTION_DAYS = 3
DEFAULT_PLAYWRIGHT_LAUNCH_DELAY_SECONDS = 3
GENERIC_HASHTAGS = {
    "#linkedin",
    "#careergrowth",
    "#buildinginpublic",
    "#personalbranding",
    "#professionaldevelopment",
}
HASHTAG_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "before",
    "between",
    "but",
    "can",
    "for",
    "from",
    "have",
    "how",
    "into",
    "just",
    "more",
    "not",
    "our",
    "post",
    "that",
    "the",
    "their",
    "this",
    "through",
    "with",
    "your",
}
HASHTAG_ACRONYMS = {
    "ai": "AI",
    "api": "API",
    "aws": "AWS",
    "crm": "CRM",
    "llm": "LLM",
    "saas": "SaaS",
    "seo": "SEO",
    "ui": "UI",
    "ux": "UX",
}
LINKEDIN_POST_EXISTING_LIMIT = 1000
LINKEDIN_OWN_POSTS_CREATOR_ID = "__linkedin_own_posts__"
LINKEDIN_OWN_POST_META_KEY = "linkedin_own_post"
SCRAPE_JOB_TERMINAL_STATUSES = {"succeeded", "failed"}

_SCRAPE_JOB_LOCK = Lock()
_SCRAPE_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_SCRAPE_JOBS: dict[str, dict[str, Any]] = {}

SAVED_ACTIONS = [
    "Get topic ideas for my posts",
    "Generate post ideas for me",
    "Generate post ideas about any topic",
    "Find audience pain points",
    "Find common mistakes around my topic",
    "Find common misconceptions people have about a topic",
    "Brainstorm post topics",
    "Brainstorm book recommendation about a topic",
    "Brainstorm documentary recommendations about a topic",
    "Brainstorm useful tools about a topic",
    *POST_CREATION_ACTIONS,
    "Change the tone of a post",
    "Be more concise",
    "Add a hook",
    "Add a CTA",
    "Add concrete examples",
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sleep_before_playwright_launch(launch_delay_seconds: float | int | None) -> None:
    delay = DEFAULT_PLAYWRIGHT_LAUNCH_DELAY_SECONDS if launch_delay_seconds is None else float(launch_delay_seconds)
    if delay > 0:
        time.sleep(delay)


def _sleep_before_creator_playwright_launch(launch_delay_seconds: float | int | None) -> None:
    if SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS <= 0:
        _sleep_before_playwright_launch(launch_delay_seconds)
        return
    delay = random.uniform(
        SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS,
        SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS,
    )
    if delay > 0:
        print(f"Waiting {delay:.1f} seconds before this LinkedIn creator Playwright launch.")
        time.sleep(delay)


def _creator_scrape_worker_count(creator_count: int) -> int:
    if creator_count > 1 and SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS > 0:
        return 1
    if LINKEDIN_AUTOMATION_MODE.strip().lower() == "burner":
        return 1
    return max(1, SCRAPE_MAX_WORKERS)


def provider_model(provider: str | None, model: str | None) -> tuple[str, str]:
    provider_value = (provider or "").strip()
    model_value = (model or "").strip()
    if provider_value.lower() == "string":
        provider_value = ""
    if model_value.lower() == "string":
        model_value = ""

    resolved_provider = (provider_value or DEFAULT_PROVIDER).lower()
    models = PROVIDER_MODELS.get(resolved_provider, [])
    resolved_model = model_value or DEFAULT_MODEL or (models[0] if models else "")
    return resolved_provider, resolved_model


def llm_config(provider: str | None = None, model: str | None = None, api_key: str | None = None) -> LLMConfig:
    resolved_provider, resolved_model = provider_model(provider, model)
    return LLMConfig(provider=resolved_provider, model=resolved_model, api_key=api_key or "")


def _default_profile(user_id: str) -> dict[str, Any]:
    return {
        "full_name": user_id.replace("-", " ").title(),
        "headline": "Professional using AI tools to create useful LinkedIn content.",
        "skills": ["AI", "LinkedIn content", "Career growth"],
        "industries": ["technology"],
        "experience_summary": "Default test profile. Replace with real professional details.",
    }


def _default_style() -> dict[str, Any]:
    return get_builtin_writing_style("Clear Builder").model_dump()


def seed_default_users(repo: DynamoRepository) -> None:
    timestamp = now_iso()
    defaults = [
        {
            "user_id": "test-user-1",
            "profile": {
                "full_name": "Zain Zia",
                "headline": "Artificial Intelligence Engineer",
                "location": "Karachi, Pakistan",
                "skills": ["Python", "LangChain", "FastAPI", "AWS", "DynamoDB"],
                "industries": ["AI", "software engineering"],
                "experience_summary": "Builds AI applications, backend APIs, and content automation workflows.",
            },
            "writing_style": get_builtin_writing_style("Clear Builder").model_dump(),
        },
        {
            "user_id": "test-user-2",
            "profile": {
                "full_name": "Mughees Khan",
                "headline": "Backend and AI Workflow Builder",
                "location": "Pakistan",
                "skills": ["Python", "Streamlit", "FastAPI", "Playwright", "LinkedIn content"],
                "industries": ["developer tools", "AI automation"],
                "experience_summary": "Experiments with practical AI tools for research, writing, and productivity.",
            },
            "writing_style": get_builtin_writing_style("Story Driven").model_dump(),
        },
    ]
    for user in defaults:
        if repo.get_user(user["user_id"]):
            continue
        user["created_at"] = timestamp
        user["updated_at"] = timestamp
        repo.put_user(user)
        print(f"Seeded default API user: {user['user_id']}")


def create_user(
    repo: DynamoRepository,
    user_id: str,
    profile: dict[str, Any],
    writing_style: dict[str, Any] | None,
) -> UserResponse:
    timestamp = now_iso()
    existing = repo.get_user(user_id)
    record = {
        "user_id": user_id,
        "profile": profile or _default_profile(user_id),
        "writing_style": writing_style or _default_style(),
        "created_at": existing.get("created_at", timestamp) if existing else timestamp,
        "updated_at": timestamp,
    }
    return UserResponse.model_validate(repo.put_user(record))


def update_user(
    repo: DynamoRepository,
    user_id: str,
    profile: dict[str, Any] | None,
    writing_style: dict[str, Any] | None,
) -> UserResponse:
    record = require_user(repo, user_id)
    if profile is not None:
        record["profile"] = profile
    if writing_style is not None:
        record["writing_style"] = writing_style
    record["updated_at"] = now_iso()
    return UserResponse.model_validate(repo.put_user(record))


def require_user(repo: DynamoRepository, user_id: str) -> dict[str, Any]:
    user = repo.get_user(user_id)
    if not user:
        raise KeyError(f"User not found: {user_id}")
    return user


def user_response(user: dict[str, Any]) -> UserResponse:
    return UserResponse.model_validate(user)


def thread_response(thread: dict[str, Any]) -> ThreadResponse:
    return ThreadResponse.model_validate(thread)


def thread_summary(thread: dict[str, Any]) -> ThreadSummary:
    return ThreadSummary.model_validate(
        {
            "thread_id": thread.get("thread_id", ""),
            "topic": thread.get("topic", ""),
            "topic_source": thread.get("topic_source", ""),
            "generation_style": thread.get("generation_style", ""),
            "created_at": thread.get("created_at", ""),
            "updated_at": thread.get("updated_at", ""),
        }
    )


def _resolve_style(user: dict[str, Any], generation_style: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(generation_style, dict):
        return generation_style
    if isinstance(generation_style, str) and generation_style.strip():
        if generation_style in {"Clear Builder", "Story Driven", "Research Analyst"}:
            return get_builtin_writing_style(generation_style).model_dump()
        style = dict(user.get("writing_style") or _default_style())
        style["requested_variation"] = generation_style
        return style
    return user.get("writing_style") or _default_style()


def _normalize_control(value: str | None, allowed: list[str], default: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if not cleaned:
        return default
    for item in allowed:
        if cleaned.lower() == item.lower():
            return item
    return cleaned[:80]


def _post_generation_instructions(
    post_length: str,
    tone: str,
    writing_style: str,
    post_variation: str = "",
    format_tags: list[str] | None = None,
    tone_tags: list[str] | None = None,
    angle_tags: list[str] | None = None,
    structure: str = "",
) -> str:
    advanced = [
        f"Variation: {post_variation}." if post_variation else "",
        f"Format preferences: {', '.join(format_tags or [])}." if format_tags else "",
        f"Additional tone signals: {', '.join(tone_tags or [])}." if tone_tags else "",
        f"Narrative angles: {', '.join(angle_tags or [])}." if angle_tags else "",
        f"Copy structure: {structure}." if structure else "",
    ]
    return (
        f"Post length: {post_length}.\n"
        f"Tone: {tone}.\n"
        f"Writing style: {writing_style}.\n"
        f"{' '.join(item for item in advanced if item)}\n"
        "Do not use a CTA template. Do not follow a prebuilt post template. "
        "Create the post directly from the topic and controls. "
        "Avoid generic hashtags such as #LinkedIn, #CareerGrowth, and #BuildingInPublic. "
        "Use only topic-specific hashtags when they genuinely fit."
    )


def _hashtag_part(token: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", token)
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower in HASHTAG_ACRONYMS:
        return HASHTAG_ACRONYMS[lower]
    if cleaned.isupper() and len(cleaned) <= 6:
        return cleaned
    return cleaned[:1].upper() + cleaned[1:].lower()


def _topic_keyword_entries(topic: str) -> list[tuple[str, int]]:
    keywords: list[tuple[str, int]] = []
    seen: set[str] = set()
    for index, token in enumerate(re.findall(r"[A-Za-z][A-Za-z0-9+.-]*", topic or "")):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", token)
        lower = cleaned.lower()
        if not cleaned or lower in HASHTAG_STOPWORDS:
            continue
        if len(cleaned) < 3 and lower not in HASHTAG_ACRONYMS:
            continue
        if lower not in seen:
            keywords.append((cleaned, index))
            seen.add(lower)
    return keywords


def _topic_hashtags(topic: str, limit: int = 3) -> list[str]:
    keyword_entries = _topic_keyword_entries(topic)
    keywords = [keyword for keyword, _ in keyword_entries]
    tags: list[str] = []

    def add_tag(parts: list[str]) -> None:
        tag = "#" + "".join(_hashtag_part(part) for part in parts if _hashtag_part(part))
        if len(tag) <= 1 or tag.lower() in GENERIC_HASHTAGS:
            return
        if tag.lower() not in {item.lower() for item in tags}:
            tags.append(tag)

    for index in range(max(len(keyword_entries) - 1, 0)):
        left, left_position = keyword_entries[index]
        right, right_position = keyword_entries[index + 1]
        if right_position != left_position + 1:
            continue
        add_tag([left, right])
        if len(tags) >= limit:
            return tags[:limit]

    for keyword in keywords:
        add_tag([keyword])
        if len(tags) >= limit:
            break

    return tags[:limit]


def _style_with_topic_hashtags(style: dict[str, Any], topic: str) -> dict[str, Any]:
    updated = dict(style or {})
    updated["hashtags"] = _topic_hashtags(topic)
    updated["hashtag_guidance"] = (
        "Use no generic growth hashtags. Prefer the provided topic-specific hashtags, "
        "or omit hashtags if none fit naturally."
    )
    return updated


def _ensure_hashtags(post: str, topic: str) -> str:
    formatted = format_linkedin_post(post)
    if not formatted:
        return formatted

    body = HASHTAG_RE.sub("", formatted)
    existing_tags = [
        tag
        for tag in HASHTAG_RE.findall(formatted)
        if tag.lower() not in GENERIC_HASHTAGS
    ]
    tags: list[str] = []
    for tag in [*existing_tags, *_topic_hashtags(topic)]:
        if tag.lower() not in {item.lower() for item in tags}:
            tags.append(tag)

    clean_body = format_linkedin_post(body)
    if not tags:
        return clean_body
    return format_linkedin_post(f"{clean_body}\n\n{' '.join(tags[:5])}")


def generate_post(repo: DynamoRepository, request: GeneratePostRequest) -> ThreadResponse:
    user = require_user(repo, request.user_id)
    config = llm_config()
    post_length = _normalize_control(request.post_length, ["Short", "Medium", "Long"], "Medium")
    tone = _normalize_control(
        request.tone,
        ["Professional", "Casual", "Conversational", "Founder voice", "Educational", "Bold", "Friendly", "Direct"],
        "Professional",
    )
    writing_style_name = _normalize_control(
        request.writing_style,
        ["Clear Builder", "Story Driven", "Research Analyst"],
        "Clear Builder",
    )
    style = _style_with_topic_hashtags(_resolve_style(user, writing_style_name), request.idea)
    generation_style_label = "Custom controls"
    profile = user.get("profile") or {}
    generation_instructions = _post_generation_instructions(
        post_length,
        tone,
        writing_style_name,
        request.post_variation,
        request.format_tags,
        request.tone_tags,
        request.angle_tags,
        request.structure,
    )

    graph_result = run_post_generation(
        {
            "workflow_mode": "generate",
            "topic": request.idea,
            "writing_style": style,
            "generation_style": generation_style_label,
            "generation_instructions": generation_instructions,
            "resume_profile": profile,
            "messages": [{"role": "user", "content": request.idea}],
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "attempts": 0,
            "max_attempts": MAX_REVIEW_ATTEMPTS,
        }
    )
    post = _ensure_hashtags(graph_result.get("final_post", ""), request.idea)
    timestamp = now_iso()
    thread = {
        "user_id": request.user_id,
        "thread_id": str(uuid4()),
        "topic": request.idea,
        "topic_source": request.topic_source,
        "generation_style": generation_style_label,
        "original_post": post,
        "current_post": post,
        "conversation": graph_result.get("messages", []),
        "provider": config.provider,
        "model": config.model,
        "source": {
            "post_length": post_length,
            "tone": tone,
            "writing_style": writing_style_name,
            "post_variation": request.post_variation,
            "format_tags": request.format_tags,
            "tone_tags": request.tone_tags,
            "angle_tags": request.angle_tags,
            "structure": request.structure,
        },
        "content_status": "in_progress",
        "writing_style_snapshot": style,
        "profile_snapshot": profile,
        "created_at": timestamp,
        "updated_at": timestamp,
        "generated_at": timestamp,
        "modified_at": "",
        "modification_count": 0,
    }
    repo.put_thread(thread)
    return thread_response(thread)


def modify_post(repo: DynamoRepository, request: ModifyPostRequest) -> ThreadResponse:
    user = require_user(repo, request.user_id)
    thread = repo.get_thread(request.user_id, request.thread_id)
    if not thread:
        raise KeyError(f"Thread not found: {request.thread_id}")

    config = llm_config()
    messages = list(thread.get("conversation", []))
    messages.append({"role": "user", "content": request.modification_message})
    graph_result = run_post_chat_edit(
        {
            "workflow_mode": "chat",
            "topic": thread.get("topic", ""),
            "writing_style": thread.get("writing_style_snapshot") or user.get("writing_style") or _default_style(),
            "resume_profile": thread.get("profile_snapshot") or user.get("profile") or {},
            "current_post": thread.get("current_post", ""),
            "messages": messages,
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "attempts": 0,
            "max_attempts": MAX_REVIEW_ATTEMPTS,
        }
    )
    timestamp = now_iso()
    thread["current_post"] = _ensure_hashtags(
        graph_result.get("final_post", thread.get("current_post", "")),
        thread.get("topic", ""),
    )
    thread["conversation"] = graph_result.get("messages", messages)
    thread["provider"] = config.provider
    thread["model"] = config.model
    thread["updated_at"] = timestamp
    thread["modified_at"] = timestamp
    thread["modification_count"] = int(thread.get("modification_count", 0)) + 1
    repo.put_thread(thread)
    return thread_response(thread)


def brainstorm(repo: DynamoRepository, request: BrainstormRequest) -> BrainstormResponse:
    user = require_user(repo, request.user_id)
    config = llm_config()
    topic = request.topic or user.get("profile", {}).get("headline", "professional growth")
    extra_details = f"{request.action}: {topic}"
    results = research_trending_topics(
        resume_profile=user.get("profile"),
        llm_config=config,
        extra_details=extra_details,
    )
    ideas = [
        {
            "title": finding.title,
            "summary": finding.summary,
            "post_angle": finding.suggested_post_angle,
            "source_url": finding.source_url,
        }
        for finding in results.findings
    ]
    if not ideas:
        ideas = [
            {
                "title": f"{request.action}: {topic}",
                "summary": f"Turn one practical lesson about {topic} into a useful LinkedIn post.",
                "post_angle": "Explain the problem, the mistake people make, and the better approach.",
                "source_url": "",
            }
        ]
    research_suggestions = [
        f"Recent examples of {topic}",
        f"Common mistakes around {topic}",
        f"Audience pain points for {topic}",
    ]
    return BrainstormResponse(
        user_id=request.user_id,
        action=request.action,
        topic=topic,
        ideas=ideas,
        research_suggestions=research_suggestions,
        provider=config.provider,
        model=config.model,
    )


def create_creator(repo: DynamoRepository, user_id: str, profile_url: str) -> CreatorResponse:
    require_user(repo, user_id)
    normalized_url = normalize_linkedin_profile_url(profile_url)
    creator_id = get_profile_id(normalized_url)
    timestamp = now_iso()
    existing = repo.get_creator(user_id, creator_id)
    if existing:
        return CreatorResponse.model_validate(
            {
                "user_id": user_id,
                "creator_id": creator_id,
                "profile_url": existing.get("profile_url", normalized_url),
                "display_name": existing.get("display_name", creator_id),
                "added_at": existing.get("added_at", timestamp),
                "updated_at": existing.get("updated_at", existing.get("added_at", timestamp)),
                "last_checked_at": existing.get("last_checked_at"),
                "seen_count": existing.get("seen_count", 0),
                "new_count": existing.get("new_count", 0),
            }
        )
    record = {
        "user_id": user_id,
        "creator_id": creator_id,
        "profile_url": normalized_url,
        "display_name": creator_id,
        "added_at": timestamp,
        "updated_at": timestamp,
        "last_checked_at": None,
        "seen_count": 0,
        "new_count": 0,
    }
    return CreatorResponse.model_validate(repo.put_creator(record))


def delete_creator_with_activities(repo: DynamoRepository, user_id: str, creator_id: str) -> DeleteResponse:
    require_user(repo, user_id)
    if not repo.get_creator(user_id, creator_id):
        raise KeyError(f"Creator not found: {creator_id}")

    deleted_activity_count = 0
    for activity in repo.list_creator_activities(user_id, creator_id, CREATOR_IMPORT_EXISTING_LIMIT):
        repo.delete_activity(user_id, creator_id, str(activity.get("post_id", "")))
        deleted_activity_count += 1
    repo.delete_creator(user_id, creator_id)
    return DeleteResponse(
        ok=True,
        message=f"Deleted creator {creator_id} and {deleted_activity_count} saved post(s).",
    )


def creator_response(creator: dict[str, Any]) -> CreatorResponse:
    return CreatorResponse.model_validate(creator)


def _creator_profile_details_response(creator: dict[str, Any]) -> CreatorProfileDetailsResponse:
    details = dict(creator.get("profile_details") or {})
    return CreatorProfileDetailsResponse(
        user_id=str(creator.get("user_id", "")),
        creator_id=str(creator.get("creator_id", "")),
        profile_url=str(creator.get("profile_url", "")),
        name=str(details.get("name", "")),
        headline=str(details.get("headline", "")),
        about=str(details.get("about", "")),
        location=str(details.get("location", "")),
        profile_image_url=str(details.get("profile_image_url", "")),
        experience=[
            str(item).strip()
            for item in details.get("experience", [])
            if str(item).strip()
        ]
        if isinstance(details.get("experience", []), list)
        else [],
        fetched_at=str(details.get("fetched_at", "")),
        source=str(details.get("source", "playwright")),
    )


def _normalize_profile_details(raw_details: dict[str, Any]) -> dict[str, Any]:
    experience = raw_details.get("experience", [])
    if not isinstance(experience, list):
        experience = []
    return {
        "name": str(raw_details.get("name", "")).strip(),
        "headline": str(raw_details.get("headline", "")).strip(),
        "about": str(raw_details.get("about", "")).strip(),
        "location": str(raw_details.get("location", "")).strip(),
        "profile_image_url": str(raw_details.get("profile_image_url", "")).strip(),
        "experience": [str(item).strip() for item in experience if str(item).strip()],
        "fetched_at": str(raw_details.get("fetched_at", now_iso())),
        "source": str(raw_details.get("source", "playwright")),
    }


def get_creator_profile_details(
    repo: DynamoRepository,
    user_id: str,
    creator_id: str,
) -> CreatorProfileDetailsResponse:
    require_user(repo, user_id)
    creator = repo.get_creator(user_id, creator_id)
    if not creator:
        raise KeyError(f"Creator not found: {creator_id}")
    return _creator_profile_details_response(creator)


def list_creator_profile_details(
    repo: DynamoRepository,
    user_id: str,
    limit: int | None = None,
) -> list[CreatorProfileDetailsResponse]:
    require_user(repo, user_id)
    return [
        _creator_profile_details_response(creator)
        for creator in repo.list_creators(user_id, limit or CREATOR_IMPORT_EXISTING_LIMIT)
    ]


def scrape_creator_profile_details(
    repo: DynamoRepository,
    request: ScrapeCreatorProfilesRequest,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ScrapeCreatorProfilesResponse:
    require_user(repo, request.user_id)
    creators = repo.list_creators(request.user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    if request.creator_ids:
        creator_id_set = set(request.creator_ids)
        creators = [creator for creator in creators if creator["creator_id"] in creator_id_set]

    errors: list[dict[str, str]] = []
    profiles: list[CreatorProfileDetailsResponse] = []

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        _sleep_before_creator_playwright_launch(request.launch_delay_seconds)
        return creator, fetch_profile_details(creator["profile_url"])

    max_workers = _creator_scrape_worker_count(len(creators))
    if max_workers == 1 and len(creators) > 1:
        print("Running creator profile scrapes sequentially with the configured inter-creator delay.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(scrape_one, creator): creator for creator in creators}
        for future in as_completed(future_map):
            creator = future_map[future]
            timestamp = now_iso()
            try:
                _, raw_details = future.result()
            except Exception as exc:
                errors.append({"creator_id": creator["creator_id"], "message": str(exc)})
                if progress_callback:
                    progress_callback(
                        {
                            "creator_id": creator["creator_id"],
                            "status": "failed",
                            "profiles_found": 0,
                            "message": str(exc),
                        }
                    )
                continue

            if raw_details.get("error"):
                if raw_details.get("error") == "linkedin_profile_not_found":
                    creator["profile_details"] = {
                        "name": "",
                        "headline": "Profile not found or unavailable",
                        "about": str(raw_details.get("message") or ""),
                        "location": "",
                        "profile_image_url": "",
                        "experience": [],
                        "fetched_at": timestamp,
                        "source": "playwright",
                    }
                errors.append(
                    {
                        "creator_id": creator["creator_id"],
                        "message": str(raw_details.get("message") or raw_details.get("error")),
                    }
                )
                creator["profile_details_checked_at"] = timestamp
                creator["updated_at"] = timestamp
                repo.put_creator(creator)
                if progress_callback:
                    progress_callback(
                        {
                            "creator_id": creator["creator_id"],
                            "status": "failed",
                            "profiles_found": 0,
                            "message": str(raw_details.get("message") or raw_details.get("error")),
                        }
                    )
                continue

            details = _normalize_profile_details(raw_details)
            creator["profile_details"] = details
            creator["profile_details_checked_at"] = details.get("fetched_at") or timestamp
            if details.get("name"):
                creator["display_name"] = details["name"]
            creator["updated_at"] = timestamp
            saved_creator = repo.put_creator(creator)
            profiles.append(_creator_profile_details_response(saved_creator))
            if progress_callback:
                progress_callback(
                    {
                        "creator_id": creator["creator_id"],
                        "status": "succeeded",
                        "profiles_found": 1,
                    }
                )

    return ScrapeCreatorProfilesResponse(
        user_id=request.user_id,
        checked_creator_ids=[creator["creator_id"] for creator in creators],
        profiles=profiles,
        errors=errors,
    )


def _activity_response(activity: dict[str, Any]) -> ActivityResponse:
    return ActivityResponse.model_validate(activity)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ElementTree.Element, child_name: str) -> str:
    for child in element:
        if _tag_name(child.tag) == child_name:
            return child.text or ""
    return ""


def _rich_text(element: ElementTree.Element) -> str:
    return "".join(child.text or "" for child in element.iter() if _tag_name(child.tag) == "t").strip()


def _decode_sheet_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _add_url_candidates(candidates: list[dict[str, str]], row_label: str, value: Any) -> None:
    text = str(value or "").strip()
    if not text:
        return
    for match in LINKEDIN_URL_RE.finditer(text):
        url = match.group(0).strip().rstrip(").,;]")
        if url:
            candidates.append({"row": row_label, "url": url})


def _creator_url_candidates_from_text(content: bytes, *, csv_mode: bool) -> list[dict[str, str]]:
    text = _decode_sheet_text(content)
    candidates: list[dict[str, str]] = []
    if csv_mode:
        reader = csv.reader(io.StringIO(text))
        for row_number, row in enumerate(reader, start=1):
            for cell in row:
                _add_url_candidates(candidates, str(row_number), cell)
        return candidates

    for row_number, line in enumerate(text.splitlines(), start=1):
        _add_url_candidates(candidates, str(row_number), line)
    return candidates


def _xlsx_shared_strings(root: ElementTree.Element) -> list[str]:
    shared_strings: list[str] = []
    for item in root.iter():
        if _tag_name(item.tag) == "si":
            shared_strings.append(_rich_text(item))
    return shared_strings


def _creator_url_candidates_from_xlsx(content: bytes) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            names = set(workbook.namelist())
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                shared_strings = _xlsx_shared_strings(shared_root)

            sheet_names = sorted(name for name in names if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
            for sheet_name in sheet_names:
                sheet_root = ElementTree.fromstring(workbook.read(sheet_name))
                sheet_number = re.search(r"sheet(\d+)\.xml$", sheet_name)
                sheet_label = sheet_number.group(1) if sheet_number else sheet_name
                for row in sheet_root.iter():
                    if _tag_name(row.tag) != "row":
                        continue
                    row_number = row.attrib.get("r", "")
                    row_label = f"sheet {sheet_label} row {row_number or '?'}"
                    for cell in row:
                        if _tag_name(cell.tag) != "c":
                            continue
                        cell_type = cell.attrib.get("t", "")
                        value = ""
                        if cell_type == "s":
                            index_text = _child_text(cell, "v")
                            if index_text.isdigit() and int(index_text) < len(shared_strings):
                                value = shared_strings[int(index_text)]
                        elif cell_type == "inlineStr":
                            value = _rich_text(cell)
                        else:
                            value = _child_text(cell, "v")
                        _add_url_candidates(candidates, row_label, value)
    except (ElementTree.ParseError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Could not read the XLSX file: {exc}") from exc
    return candidates


def _creator_url_candidates_from_file(file_name: str, content: bytes) -> list[dict[str, str]]:
    lower_name = (file_name or "").lower()
    if lower_name.endswith(".xls"):
        raise ValueError("Only .csv, .txt, and .xlsx files are supported. Export old .xls files as .xlsx or CSV.")
    if lower_name.endswith(".xlsx") or content[:2] == b"PK":
        return _creator_url_candidates_from_xlsx(content)
    return _creator_url_candidates_from_text(content, csv_mode=lower_name.endswith(".csv"))


def import_creators_from_file(
    repo: DynamoRepository,
    user_id: str,
    file_name: str,
    content: bytes,
) -> BulkCreatorImportResponse:
    require_user(repo, user_id)
    candidates = _creator_url_candidates_from_file(file_name, content)
    existing_creators = repo.list_creators(user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    existing_creator_ids = {creator.get("creator_id", "") for creator in existing_creators}
    file_creator_ids: set[str] = set()
    added_creators: list[CreatorResponse] = []
    skipped_existing_creator_ids: list[str] = []
    skipped_duplicate_creator_ids: list[str] = []
    skipped_existing_creators: list[dict[str, str]] = []
    skipped_duplicate_creators: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for candidate in candidates:
        row_label = candidate.get("row", "")
        raw_url = candidate.get("url", "")
        try:
            normalized_url = normalize_linkedin_profile_url(raw_url)
            creator_id = get_profile_id(normalized_url)
        except ValueError as exc:
            errors.append({"row": row_label, "url": raw_url, "message": str(exc)})
            continue

        if creator_id in file_creator_ids:
            _append_unique(skipped_duplicate_creator_ids, creator_id)
            skipped_duplicate_creators.append(
                {
                    "row": row_label,
                    "url": raw_url,
                    "normalized_url": normalized_url,
                    "creator_id": creator_id,
                    "reason": "Duplicate URL in uploaded file",
                }
            )
            continue
        if creator_id in existing_creator_ids:
            _append_unique(skipped_existing_creator_ids, creator_id)
            skipped_existing_creators.append(
                {
                    "row": row_label,
                    "url": raw_url,
                    "normalized_url": normalized_url,
                    "creator_id": creator_id,
                    "reason": "Already tracked in database",
                }
            )
            continue

        creator = create_creator(repo, user_id, normalized_url)
        added_creators.append(creator)
        file_creator_ids.add(creator.creator_id)

    if not candidates:
        errors.append({"row": "", "url": "", "message": "No LinkedIn creator URLs were found in the uploaded file."})

    return BulkCreatorImportResponse(
        user_id=user_id,
        total_urls=len(candidates),
        added_creators=added_creators,
        skipped_existing_creator_ids=skipped_existing_creator_ids,
        skipped_duplicate_creator_ids=skipped_duplicate_creator_ids,
        skipped_existing_creators=skipped_existing_creators,
        skipped_duplicate_creators=skipped_duplicate_creators,
        errors=errors,
    )


def preview_creators_from_file(
    repo: DynamoRepository,
    user_id: str,
    file_name: str,
    content: bytes,
) -> BulkCreatorPreviewResponse:
    require_user(repo, user_id)
    candidates = _creator_url_candidates_from_file(file_name, content)
    existing_creators = repo.list_creators(user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    existing_creator_ids = {creator.get("creator_id", "") for creator in existing_creators}
    file_creator_ids: set[str] = set()
    corrected_creators: list[dict[str, str]] = []
    new_creators: list[dict[str, str]] = []
    existing_preview_creators: list[dict[str, str]] = []
    duplicate_creators: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for candidate in candidates:
        row_label = candidate.get("row", "")
        raw_url = candidate.get("url", "")
        try:
            normalized_url = normalize_linkedin_profile_url(raw_url)
            creator_id = get_profile_id(normalized_url)
        except ValueError as exc:
            errors.append({"row": row_label, "url": raw_url, "message": str(exc)})
            continue

        item = {
            "row": row_label,
            "url": raw_url,
            "normalized_url": normalized_url,
            "creator_id": creator_id,
        }
        if creator_id in file_creator_ids:
            duplicate_creators.append({**item, "reason": "Duplicate URL in uploaded file"})
            continue

        corrected_creators.append(item)
        file_creator_ids.add(creator_id)
        if creator_id in existing_creator_ids:
            existing_preview_creators.append({**item, "reason": "Already tracked in database"})
        else:
            new_creators.append(item)

    if not candidates:
        errors.append({"row": "", "url": "", "message": "No LinkedIn creator URLs were found in the uploaded file."})

    return BulkCreatorPreviewResponse(
        user_id=user_id,
        total_urls=len(candidates),
        corrected_creators=corrected_creators,
        new_creators=new_creators,
        existing_creators=existing_preview_creators,
        duplicate_creators=duplicate_creators,
        errors=errors,
    )


def _hours_from_linkedin_time_text(posted_at_text: str) -> float | None:
    text = re.sub(r"\s+", " ", str(posted_at_text or "").lower())
    text = text.replace("•", " ").replace("·", " ").strip()
    if not text:
        return None
    if any(marker in text for marker in ("just now", "now", "moments ago", "seconds ago")):
        return 0.0
    if any(marker in text for marker in ("a minute ago", "1 minute ago")):
        return 1 / 60
    if any(marker in text for marker in ("an hour ago", "a hour ago", "1 hour ago")):
        return 1.0
    if "yesterday" in text:
        return 24.0
    if re.search(r"\b\d+\s*(?:w|wk|wks|week|weeks|mo|month|months|y|yr|yrs|year|years)\b", text):
        return None

    minute_match = re.search(r"\b(\d+)\s*(?:m|min|mins|minute|minutes)\b", text)
    if minute_match:
        return int(minute_match.group(1)) / 60
    hour_match = re.search(r"\b(\d+)\s*(?:h|hr|hrs|hour|hours)\b", text)
    if hour_match:
        return float(hour_match.group(1))
    day_match = re.search(r"\b(\d+)\s*(?:d|day|days)\b", text)
    if day_match:
        return float(day_match.group(1)) * 24
    return None


def _parse_activity_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _estimated_posted_at(raw_post: dict[str, Any]) -> datetime | None:
    hours = _hours_from_linkedin_time_text(str(raw_post.get("posted_at_text", "")))
    if hours is None:
        return None
    fetched_at = _parse_activity_datetime(raw_post.get("fetched_at")) or datetime.now(UTC)
    return fetched_at - timedelta(hours=hours)


def _is_post_inside_window(raw_post: dict[str, Any], window_hours: int) -> bool:
    posted_at = _estimated_posted_at(raw_post)
    if posted_at is None:
        return False
    return posted_at >= datetime.now(UTC) - timedelta(hours=window_hours)


def prune_old_activities(
    repo: DynamoRepository,
    user_id: str,
    retention_days: int = RECENT_ACTIVITY_RETENTION_DAYS,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    deleted_count = 0
    for creator in repo.list_creators(user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT):
        creator_id = str(creator.get("creator_id", ""))
        if not creator_id:
            continue
        for activity in repo.list_creator_activities(user_id, creator_id, limit=CREATOR_IMPORT_EXISTING_LIMIT):
            fetched_at = _parse_activity_datetime(activity.get("fetched_at"))
            if fetched_at is None or fetched_at >= cutoff:
                continue
            post_id = str(activity.get("post_id", ""))
            if not post_id:
                continue
            repo.delete_activity(user_id, creator_id, post_id)
            deleted_count += 1
    return deleted_count


def _normalize_activity(user_id: str, creator: dict[str, Any], raw_post: dict[str, Any], is_new: bool) -> dict[str, Any]:
    raw_text = str(raw_post.get("raw_text", "")).strip()
    content_hash = str(
        raw_post.get("content_hash")
        or hashlib.sha256(" ".join(raw_text.lower().split()).encode("utf-8")).hexdigest()
    )
    post_id = str(raw_post.get("post_id") or content_hash)
    return {
        "user_creator_id": f"{user_id}#{creator['creator_id']}",
        "user_id": user_id,
        "creator_id": creator["creator_id"],
        "post_id": post_id,
        "post_url": str(raw_post.get("post_url", "")),
        "raw_text": raw_text,
        "author_name": str(raw_post.get("author_name", creator.get("display_name", ""))),
        "posted_at_text": str(raw_post.get("posted_at_text", "")),
        "is_repost": bool(raw_post.get("is_repost", False)),
        "repost_text": str(raw_post.get("repost_text", "")),
        "original_post_text": str(raw_post.get("original_post_text", "")),
        "original_author_name": str(raw_post.get("original_author_name", "")),
        "original_author_url": str(raw_post.get("original_author_url", "")),
        "fetched_at": str(raw_post.get("fetched_at", now_iso())),
        "content_hash": content_hash,
        "source": str(raw_post.get("source", "playwright")),
        "is_new": is_new,
    }


def scrape_creators(repo: DynamoRepository, request: ScrapeCreatorsRequest) -> ScrapeCreatorsResponse:
    require_user(repo, request.user_id)
    creators = repo.list_creators(request.user_id, limit=API_LIST_LIMIT)
    if request.creator_ids:
        creator_id_set = set(request.creator_ids)
        creators = [creator for creator in creators if creator["creator_id"] in creator_id_set]
    pruned_count = prune_old_activities(repo, request.user_id)
    if pruned_count:
        print(f"Pruned {pruned_count} scraped post(s) older than {RECENT_ACTIVITY_RETENTION_DAYS} days.")

    errors: list[dict[str, str]] = []
    new_activities: list[ActivityResponse] = []

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        _sleep_before_creator_playwright_launch(request.launch_delay_seconds)
        posts = fetch_recent_profile_posts(creator["profile_url"], max_posts=request.max_posts)
        return creator, posts

    max_workers = _creator_scrape_worker_count(len(creators))
    if max_workers == 1 and len(creators) > 1:
        print("Running creator post scrapes sequentially with the configured inter-creator delay.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(scrape_one, creator): creator for creator in creators}
        for future in as_completed(future_map):
            creator = future_map[future]
            timestamp = now_iso()
            try:
                _, posts = future.result()
            except Exception as exc:
                errors.append({"creator_id": creator["creator_id"], "message": str(exc)})
                continue

            if posts and isinstance(posts[0], dict) and posts[0].get("error"):
                errors.append(
                    {
                        "creator_id": creator["creator_id"],
                        "message": str(posts[0].get("message") or posts[0].get("error")),
                    }
                )
                creator["last_checked_at"] = timestamp
                repo.put_creator(creator)
                continue

            creator_new_count = 0
            for post in posts:
                if not isinstance(post, dict) or not str(post.get("raw_text", "")).strip():
                    continue
                probe = _normalize_activity(request.user_id, creator, post, is_new=False)
                existing = repo.get_activity(request.user_id, creator["creator_id"], probe["post_id"])
                if existing:
                    continue
                activity = _normalize_activity(request.user_id, creator, post, is_new=True)
                repo.put_activity(activity)
                new_activities.append(_activity_response(activity))
                creator_new_count += 1

            creator["last_checked_at"] = timestamp
            creator["seen_count"] = len(repo.list_creator_activities(request.user_id, creator["creator_id"], API_LIST_LIMIT))
            creator["new_count"] = creator_new_count
            creator["updated_at"] = timestamp
            repo.put_creator(creator)

    _save_creator_post_scrape_metrics(
        repo,
        request.user_id,
        latest_post_count=len(new_activities),
        newly_saved_count=len(new_activities),
    )
    return ScrapeCreatorsResponse(
        user_id=request.user_id,
        checked_creator_ids=[creator["creator_id"] for creator in creators],
        new_activities=new_activities,
        errors=errors,
    )


def scrape_creators_recent_24h(
    repo: DynamoRepository,
    request: RecentScrapeCreatorsRequest,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> RecentScrapeCreatorsResponse:
    require_user(repo, request.user_id)
    creators = repo.list_creators(request.user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    if request.creator_ids:
        creator_id_set = set(request.creator_ids)
        creators = [creator for creator in creators if creator["creator_id"] in creator_id_set]
    pruned_count = prune_old_activities(repo, request.user_id)
    if pruned_count:
        print(f"Pruned {pruned_count} scraped post(s) older than {RECENT_ACTIVITY_RETENTION_DAYS} days.")

    errors: list[dict[str, str]] = []
    activities: list[ActivityResponse] = []
    newly_saved_count = 0

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        _sleep_before_creator_playwright_launch(request.launch_delay_seconds)
        posts = fetch_recent_profile_posts(creator["profile_url"], max_posts=request.max_posts)
        return creator, posts

    max_workers = _creator_scrape_worker_count(len(creators))
    if max_workers == 1 and len(creators) > 1:
        print("Running creator post scrapes sequentially with the configured inter-creator delay.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(scrape_one, creator): creator for creator in creators}
        for future in as_completed(future_map):
            creator = future_map[future]
            timestamp = now_iso()
            try:
                _, posts = future.result()
            except Exception as exc:
                errors.append({"creator_id": creator["creator_id"], "message": str(exc)})
                if progress_callback:
                    progress_callback(
                        {
                            "creator_id": creator["creator_id"],
                            "status": "failed",
                            "posts_found": 0,
                            "message": str(exc),
                        }
                    )
                continue

            if posts and isinstance(posts[0], dict) and posts[0].get("error"):
                message = str(posts[0].get("message") or posts[0].get("error"))
                errors.append({"creator_id": creator["creator_id"], "message": message})
                creator["last_checked_at"] = timestamp
                repo.put_creator(creator)
                if progress_callback:
                    progress_callback(
                        {
                            "creator_id": creator["creator_id"],
                            "status": "failed",
                            "posts_found": 0,
                            "message": message,
                        }
                    )
                continue

            creator_new_count = 0
            creator_posts_found = 0
            for post in posts:
                if not isinstance(post, dict) or not str(post.get("raw_text", "")).strip():
                    continue
                if not _is_post_inside_window(post, request.window_hours):
                    continue

                probe = _normalize_activity(request.user_id, creator, post, is_new=False)
                existing = repo.get_activity(request.user_id, creator["creator_id"], probe["post_id"])
                activity = _normalize_activity(request.user_id, creator, post, is_new=existing is None)
                if existing and existing.get("engagement"):
                    activity["engagement"] = existing["engagement"]
                repo.put_activity(activity)
                activities.append(_activity_response(activity))
                if existing is None:
                    creator_new_count += 1
                    newly_saved_count += 1
                creator_posts_found += 1

            creator["last_checked_at"] = timestamp
            creator["seen_count"] = len(repo.list_creator_activities(request.user_id, creator["creator_id"], API_LIST_LIMIT))
            creator["new_count"] = creator_new_count
            creator["updated_at"] = timestamp
            repo.put_creator(creator)
            if progress_callback:
                progress_callback(
                    {
                        "creator_id": creator["creator_id"],
                        "status": "succeeded",
                        "posts_found": creator_posts_found,
                    }
                )

    _save_creator_post_scrape_metrics(
        repo,
        request.user_id,
        latest_post_count=len(activities),
        newly_saved_count=newly_saved_count,
    )
    return RecentScrapeCreatorsResponse(
        user_id=request.user_id,
        checked_creator_ids=[creator["creator_id"] for creator in creators],
        window_hours=request.window_hours,
        activities=activities,
        errors=errors,
    )


def _target_creator_count(
    repo: DynamoRepository,
    user_id: str,
    creator_ids: list[str] | None = None,
) -> int:
    creators = repo.list_creators(user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    if creator_ids:
        creator_id_set = set(creator_ids)
        creators = [creator for creator in creators if creator["creator_id"] in creator_id_set]
    return len(creators)


def _job_response(record: dict[str, Any]) -> ScrapeJobStatusResponse:
    return ScrapeJobStatusResponse.model_validate(record)


def _job_start_response(record: dict[str, Any]) -> ScrapeJobStartResponse:
    return ScrapeJobStartResponse(
        job_id=str(record["job_id"]),
        job_type=str(record["job_type"]),
        user_id=str(record["user_id"]),
        status=str(record["status"]),
        status_url=f"/scrape-jobs/{record['job_id']}",
        total_creators=int(record.get("total_creators") or 0),
        created_at=str(record.get("created_at", "")),
    )


def _save_scrape_job(record: dict[str, Any]) -> None:
    with _SCRAPE_JOB_LOCK:
        _SCRAPE_JOBS[str(record["job_id"])] = dict(record)


def _update_scrape_job(job_id: str, **updates: Any) -> None:
    with _SCRAPE_JOB_LOCK:
        current = dict(_SCRAPE_JOBS.get(job_id) or {})
        if not current:
            return
        current.update(updates)
        current["updated_at"] = now_iso()
        _SCRAPE_JOBS[job_id] = current


def _scrape_job_progress(job_id: str, job_type: str) -> Callable[[dict[str, Any]], None]:
    def update(event: dict[str, Any]) -> None:
        with _SCRAPE_JOB_LOCK:
            current = dict(_SCRAPE_JOBS.get(job_id) or {})
            if not current:
                return
            current["scraped_creators"] = int(current.get("scraped_creators") or 0) + 1
            current["current_creator_id"] = str(event.get("creator_id", ""))
            if job_type == "creator_posts":
                current["total_posts"] = int(current.get("total_posts") or 0) + int(event.get("posts_found") or 0)
                current["message"] = (
                    f"Scraped {current['scraped_creators']} of {current.get('total_creators', 0)} creators; "
                    f"{current.get('total_posts', 0)} posts found."
                )
            else:
                current["scraped_profiles"] = int(current.get("scraped_profiles") or 0) + int(event.get("profiles_found") or 0)
                current["message"] = (
                    f"Scraped {current['scraped_creators']} of {current.get('total_creators', 0)} profiles."
                )
            if event.get("status") == "failed":
                errors = list(current.get("errors") or [])
                errors.append(
                    {
                        "creator_id": str(event.get("creator_id", "")),
                        "message": str(event.get("message", "Scrape failed.")),
                    }
                )
                current["errors"] = errors
            current["updated_at"] = now_iso()
            _SCRAPE_JOBS[job_id] = current

    return update


def _create_scrape_job(
    repo: DynamoRepository,
    user_id: str,
    job_type: str,
    total_creators: int,
    runner: Callable[[str], None],
) -> ScrapeJobStartResponse:
    require_user(repo, user_id)
    timestamp = now_iso()
    job_id = f"SCRAPE-{job_type}-{uuid4()}"
    record = {
        "job_id": job_id,
        "job_type": job_type,
        "user_id": user_id,
        "status": "queued",
        "created_at": timestamp,
        "started_at": "",
        "updated_at": timestamp,
        "completed_at": "",
        "total_creators": total_creators,
        "scraped_creators": 0,
        "total_posts": 0,
        "scraped_profiles": 0,
        "current_creator_id": "",
        "message": "Queued.",
        "errors": [],
        "result": {},
    }
    _save_scrape_job(record)
    _SCRAPE_JOB_EXECUTOR.submit(runner, job_id)
    return _job_start_response(record)


def start_recent_scrape_job(
    repo: DynamoRepository,
    request: RecentScrapeCreatorsRequest,
) -> ScrapeJobStartResponse:
    total_creators = _target_creator_count(repo, request.user_id, request.creator_ids)

    def run(job_id: str) -> None:
        _update_scrape_job(job_id, status="running", started_at=now_iso(), message="Scraping creator posts.")
        try:
            response = scrape_creators_recent_24h(
                repo,
                request,
                progress_callback=_scrape_job_progress(job_id, "creator_posts"),
            )
            _update_scrape_job(
                job_id,
                status="succeeded",
                completed_at=now_iso(),
                total_posts=len(response.activities),
                errors=response.errors,
                result=response.model_dump(),
                message=(
                    f"Completed {len(response.checked_creator_ids)} creator scrape"
                    f"{'' if len(response.checked_creator_ids) == 1 else 's'}; "
                    f"{len(response.activities)} posts found."
                ),
            )
        except Exception as exc:
            _update_scrape_job(
                job_id,
                status="failed",
                completed_at=now_iso(),
                errors=[{"message": str(exc)}],
                message=str(exc),
            )

    return _create_scrape_job(repo, request.user_id, "creator_posts", total_creators, run)


def start_profile_scrape_job(
    repo: DynamoRepository,
    request: ScrapeCreatorProfilesRequest,
) -> ScrapeJobStartResponse:
    total_creators = _target_creator_count(repo, request.user_id, request.creator_ids)

    def run(job_id: str) -> None:
        _update_scrape_job(job_id, status="running", started_at=now_iso(), message="Scraping creator profiles.")
        try:
            response = scrape_creator_profile_details(
                repo,
                request,
                progress_callback=_scrape_job_progress(job_id, "creator_profiles"),
            )
            _update_scrape_job(
                job_id,
                status="succeeded",
                completed_at=now_iso(),
                scraped_profiles=len(response.profiles),
                errors=response.errors,
                result=response.model_dump(),
                message=(
                    f"Completed {len(response.checked_creator_ids)} profile scrape"
                    f"{'' if len(response.checked_creator_ids) == 1 else 's'}; "
                    f"{len(response.profiles)} profiles saved."
                ),
            )
        except Exception as exc:
            _update_scrape_job(
                job_id,
                status="failed",
                completed_at=now_iso(),
                errors=[{"message": str(exc)}],
                message=str(exc),
            )

    return _create_scrape_job(repo, request.user_id, "creator_profiles", total_creators, run)


def get_scrape_job(job_id: str) -> ScrapeJobStatusResponse:
    with _SCRAPE_JOB_LOCK:
        record = dict(_SCRAPE_JOBS.get(job_id) or {})
    if not record:
        raise KeyError(f"Scrape job not found: {job_id}")
    return _job_response(record)


def list_all_activities(repo: DynamoRepository, user_id: str, limit: int | None = None) -> list[ActivityResponse]:
    require_user(repo, user_id)
    activities: list[ActivityResponse] = []
    for creator in repo.list_creators(user_id, limit=limit or API_LIST_LIMIT):
        activities.extend(
            _activity_response(activity)
            for activity in repo.list_creator_activities(user_id, creator["creator_id"], limit or API_LIST_LIMIT)
    )
    activities.sort(key=lambda item: item.fetched_at, reverse=True)
    return activities[: limit or API_LIST_LIMIT]


def _activity_to_dict(activity: ActivityResponse | dict[str, Any]) -> dict[str, Any]:
    if isinstance(activity, dict):
        return activity
    return activity.model_dump()


def _creator_needs_scraping(creator: dict[str, Any], now: datetime) -> bool:
    last_checked = _parse_activity_datetime(creator.get("last_checked_at"))
    if last_checked is None:
        return True
    return last_checked <= now - timedelta(hours=SCRAPING_STALE_AFTER_HOURS)


def _creator_recently_added(creator: dict[str, Any], now: datetime) -> bool:
    added_at = _parse_activity_datetime(creator.get("added_at"))
    if added_at is None:
        return False
    return added_at.date() == now.date()


def _save_creator_post_scrape_metrics(
    repo: DynamoRepository,
    user_id: str,
    latest_post_count: int,
    newly_saved_count: int,
) -> None:
    user = require_user(repo, user_id)
    existing_stats = dict(user.get("dashboard_stats") or {})
    current_saved_count = len(list_all_activities(repo, user_id, CREATOR_IMPORT_EXISTING_LIMIT))
    if "total_scraped_posts_count" in existing_stats:
        total_scraped_posts_count = int(existing_stats.get("total_scraped_posts_count") or 0) + newly_saved_count
    else:
        total_scraped_posts_count = max(
            current_saved_count,
            int(existing_stats.get("activity_count") or 0),
        )
    existing_stats.update(
        {
            "activity_count": current_saved_count,
            "total_scraped_posts_count": total_scraped_posts_count,
            "new_posts_from_last_scrape_count": latest_post_count,
            "last_creator_post_scrape_at": now_iso(),
        }
    )
    repo.put_user({**user, "dashboard_stats": existing_stats})


def build_dashboard_stats(
    creators: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    activities: list[ActivityResponse | dict[str, Any]],
    existing_stats: dict[str, Any] | None = None,
) -> DashboardStatsResponse:
    now = datetime.now(UTC)
    activity_dicts = [_activity_to_dict(activity) for activity in activities]
    saved_stats = existing_stats or {}
    activity_count = len(activity_dicts)
    return DashboardStatsResponse(
        creator_count=len(creators),
        thread_count=len(threads),
        activity_count=activity_count,
        total_scraped_posts_count=max(
            activity_count,
            int(saved_stats.get("total_scraped_posts_count") or 0),
        ),
        new_posts_today_count=sum(1 for activity in activity_dicts if _is_post_inside_window(activity, 24)),
        new_posts_from_last_scrape_count=int(
            saved_stats.get("new_posts_from_last_scrape_count")
            if "new_posts_from_last_scrape_count" in saved_stats
            else sum(int(creator.get("new_count") or 0) for creator in creators)
        ),
        needs_scraping_count=sum(1 for creator in creators if _creator_needs_scraping(creator, now)),
        recently_added_count=sum(1 for creator in creators if _creator_recently_added(creator, now)),
        recently_added_window_days=RECENTLY_ADDED_WINDOW_DAYS,
        scraping_stale_after_hours=SCRAPING_STALE_AFTER_HOURS,
        updated_at=now.isoformat(),
    )


def list_recent_activities_from_db(
    repo: DynamoRepository,
    user_id: str,
    limit: int | None = None,
    window_hours: int = 24,
) -> RecentActivitiesResponse:
    require_user(repo, user_id)
    capped_limit = limit or API_LIST_LIMIT
    activities: list[ActivityResponse] = []
    for creator in repo.list_creators(user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT):
        for activity in repo.list_creator_activities(user_id, creator["creator_id"], limit=capped_limit):
            if not _is_post_inside_window(activity, window_hours):
                continue
            activities.append(_activity_response(activity))

    activities.sort(key=lambda item: item.fetched_at, reverse=True)
    return RecentActivitiesResponse(
        user_id=user_id,
        window_hours=window_hours,
        activities=activities[:capped_limit],
    )


def _normalize_comment_style(style: str | None, legacy_topic: str | None = None) -> str:
    cleaned = (style or legacy_topic or "").strip()
    if not cleaned:
        return COMMENT_TOPICS[0]
    for topic in COMMENT_TOPICS:
        if cleaned.lower() == topic.lower():
            return topic
    return cleaned


def _normalize_comment_tone(tone: str | None) -> str:
    return _normalize_control(
        tone,
        ["Professional", "Casual", "Friendly", "Direct", "Thoughtful", "Founder voice", "Conversational"],
        "Professional",
    )


def _normalize_comment_length(length: str | None) -> str:
    return _normalize_control(length, ["Short", "Medium", "Long"], "Medium")


def _format_comment(comment: str, length: str = "Medium") -> str:
    cleaned = re.sub(r"\s+", " ", comment or "").strip()
    cleaned = cleaned.replace("#", "").strip()
    if not cleaned:
        return "This is a useful angle. The practical takeaway is worth testing in a real workflow."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    sentence_limit = {"Short": 1, "Medium": 2, "Long": 3}.get(length, 2)
    compact = " ".join(sentence for sentence in sentences[:sentence_limit] if sentence).strip()
    words = compact.split()
    max_words = {"Short": 28, "Medium": 55, "Long": 90}.get(length, 55)
    if len(words) > max_words:
        compact = " ".join(words[:max_words]).rstrip(".,;:") + "."
    return compact


def _comment_fallback(comment_style: str, creator_post: str, tone: str = "Professional", length: str = "Medium") -> GeneratedComment:
    snippet = " ".join(creator_post.split()[:18])
    if comment_style == "Congratulate":
        comment = "Congrats on sharing this. The practical breakdown makes the idea much easier to act on."
    elif comment_style == "Agree":
        comment = "Agreed. The strongest point here is that the workflow matters as much as the tool itself."
    elif comment_style == "Disagree":
        comment = "I see the point, though I would be careful about treating this as universal. The right answer still depends on the workflow and constraints."
    elif comment_style == "Challenge":
        comment = "Good point. The question I would ask is: what is the first signal that this approach is actually working in production?"
    elif comment_style == "Expert Insight":
        comment = "The underrated part is the operating model around this. Without review loops and clear ownership, even strong tools create noisy outputs."
    else:
        comment = f"Useful angle. One thing I would add: connect this back to the smallest repeatable workflow, not just the headline idea. Context: {snippet}"
    if tone == "Casual":
        comment = comment.replace("The practical", "I like the practical")
    return GeneratedComment(comment=_format_comment(comment, length), rationale="Deterministic fallback comment.")


def _require_creator_activity(
    repo: DynamoRepository,
    user_id: str,
    creator_id: str,
    post_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    user = require_user(repo, user_id)
    creator = repo.get_creator(user_id, creator_id)
    if not creator:
        raise KeyError(f"Creator not found: {creator_id}")
    activity = repo.get_activity(user_id, creator_id, post_id)
    if not activity:
        raise KeyError(f"Creator post not found: {post_id}")
    return user, creator, activity


def _comment_response(activity: dict[str, Any], comment_record: dict[str, Any]) -> CommentResponse:
    return CommentResponse(
        user_id=activity["user_id"],
        creator_id=activity["creator_id"],
        post_id=activity["post_id"],
        thread_id=str(comment_record.get("thread_id", "")),
        comment_topic=str(comment_record.get("topic", comment_record.get("style", ""))),
        style=str(comment_record.get("style", comment_record.get("topic", "Add Value"))),
        tone=str(comment_record.get("tone", "Professional")),
        length=str(comment_record.get("length", "Medium")),
        comment=str(comment_record.get("text", "")),
        provider=str(comment_record.get("provider", "")),
        model=str(comment_record.get("model", "")),
        generated_at=str(comment_record.get("generated_at", "")),
        commented=bool(comment_record.get("commented", False)),
        modification_count=int(comment_record.get("modification_count", 0) or 0),
        conversation=list(comment_record.get("conversation") or []),
    )


def generate_comment(repo: DynamoRepository, request: GenerateCommentRequest) -> CommentResponse:
    user, _, activity = _require_creator_activity(repo, request.user_id, request.creator_id, request.post_id)
    config = llm_config()
    comment_style = _normalize_comment_style(request.style, request.comment_topic)
    tone = _normalize_comment_tone(request.tone)
    length = _normalize_comment_length(request.length)
    creator_post = str(activity.get("raw_text", ""))
    generated = invoke_structured(
        config=config,
        schema=GeneratedComment,
        system_prompt=COMMENT_GENERATION_SYSTEM_PROMPT,
        user_prompt=COMMENT_GENERATION_USER_PROMPT.format(
            creator_post=creator_post[:5000],
            comment_style=comment_style,
            tone=tone,
            length=length,
            resume_profile=json.dumps(user.get("profile") or {}, ensure_ascii=True, indent=2),
        ),
        fallback_factory=lambda: _comment_fallback(comment_style, creator_post, tone, length),
    )
    timestamp = now_iso()
    text = _format_comment(generated.comment, length)
    thread_id = str(uuid4())
    conversation = [
        {
            "role": "user",
            "content": (
                f"Generate a {length.lower()} {tone.lower()} LinkedIn comment "
                f"using {comment_style} style."
            ),
        },
        {"role": "assistant", "content": text},
    ]
    repo.put_thread(
        {
            "user_id": request.user_id,
            "thread_id": thread_id,
            "topic": f"Comment on {activity.get('author_name') or activity.get('creator_id')}",
            "topic_source": "comment_generation",
            "generation_style": comment_style,
            "original_post": text,
            "current_post": text,
            "conversation": conversation,
            "provider": config.provider,
            "model": config.model,
            "source": {
                "type": "comment",
                "creator_id": activity["creator_id"],
                "post_id": activity["post_id"],
                "post_url": activity.get("post_url", ""),
                "comment_style": comment_style,
                "tone": tone,
                "length": length,
            },
            "writing_style_snapshot": {},
            "profile_snapshot": user.get("profile") or {},
            "created_at": timestamp,
            "updated_at": timestamp,
            "generated_at": timestamp,
            "modified_at": "",
            "modification_count": 0,
        }
    )
    engagement = dict(activity.get("engagement") or {})
    previous_comment = dict(engagement.get("comment") or {})
    comment_record = {
        **previous_comment,
        "thread_id": thread_id,
        "topic": comment_style,
        "style": comment_style,
        "tone": tone,
        "length": length,
        "text": text,
        "generated_at": timestamp,
        "provider": config.provider,
        "model": config.model,
        "modification_count": 0,
        "conversation": conversation,
    }
    engagement["comment"] = comment_record
    activity["engagement"] = engagement
    repo.put_activity(activity)
    return _comment_response(activity, comment_record)


def modify_comment(repo: DynamoRepository, request: ModifyCommentRequest) -> CommentResponse:
    user = require_user(repo, request.user_id)
    thread = repo.get_thread(request.user_id, request.thread_id)
    if not thread:
        raise KeyError(f"Thread not found: {request.thread_id}")
    source = dict(thread.get("source") or {})
    if source.get("type") != "comment":
        raise KeyError(f"Comment thread not found: {request.thread_id}")

    creator_id = str(source.get("creator_id", ""))
    post_id = str(source.get("post_id", ""))
    _, _, activity = _require_creator_activity(repo, request.user_id, creator_id, post_id)

    comment_style = _normalize_comment_style(request.style or source.get("comment_style"))
    tone = _normalize_comment_tone(request.tone or source.get("tone"))
    length = _normalize_comment_length(request.length or source.get("length"))
    current_comment = str(thread.get("current_post", ""))
    messages = list(thread.get("conversation") or [])
    messages.append({"role": "user", "content": request.modification_message})
    config = llm_config()
    generated = invoke_structured(
        config=config,
        schema=GeneratedComment,
        system_prompt=COMMENT_MODIFICATION_SYSTEM_PROMPT,
        user_prompt=COMMENT_MODIFICATION_USER_PROMPT.format(
            creator_post=str(activity.get("raw_text", ""))[:5000],
            current_comment=current_comment,
            user_request=request.modification_message,
            conversation_history=json.dumps(messages[-10:], ensure_ascii=True, indent=2),
            comment_style=comment_style,
            tone=tone,
            length=length,
            resume_profile=json.dumps(user.get("profile") or {}, ensure_ascii=True, indent=2),
        ),
        fallback_factory=lambda: GeneratedComment(
            comment=_format_comment(f"{current_comment} {request.modification_message}", length),
            rationale="Deterministic fallback comment modification.",
        ),
    )
    timestamp = now_iso()
    revised_comment = _format_comment(generated.comment, length)
    messages.append({"role": "assistant", "content": revised_comment})
    modification_count = int(thread.get("modification_count", 0) or 0) + 1

    thread["current_post"] = revised_comment
    thread["conversation"] = messages
    thread["provider"] = config.provider
    thread["model"] = config.model
    thread["updated_at"] = timestamp
    thread["modified_at"] = timestamp
    thread["modification_count"] = modification_count
    source["comment_style"] = comment_style
    source["tone"] = tone
    source["length"] = length
    thread["source"] = source
    repo.put_thread(thread)

    engagement = dict(activity.get("engagement") or {})
    comment_record = dict(engagement.get("comment") or {})
    comment_record.update(
        {
            "thread_id": request.thread_id,
            "topic": comment_style,
            "style": comment_style,
            "tone": tone,
            "length": length,
            "text": revised_comment,
            "generated_at": str(comment_record.get("generated_at", thread.get("generated_at", timestamp))),
            "modified_at": timestamp,
            "provider": config.provider,
            "model": config.model,
            "modification_count": modification_count,
            "conversation": messages,
        }
    )
    engagement["comment"] = comment_record
    activity["engagement"] = engagement
    repo.put_activity(activity)
    return _comment_response(activity, comment_record)


def mark_activity_commented(repo: DynamoRepository, request: MarkCommentedRequest) -> CommentResponse:
    _, _, activity = _require_creator_activity(repo, request.user_id, request.creator_id, request.post_id)
    timestamp = now_iso()
    engagement = dict(activity.get("engagement") or {})
    comment_record = dict(engagement.get("comment") or {})
    if request.comment_text is not None:
        comment_record["text"] = _format_comment(request.comment_text, str(comment_record.get("length", "Medium")))
    comment_record["commented"] = request.commented
    comment_record["marked_at"] = timestamp
    engagement["comment"] = comment_record
    activity["engagement"] = engagement
    repo.put_activity(activity)
    return _comment_response(activity, comment_record)


def list_commented_activities(
    repo: DynamoRepository,
    user_id: str,
    limit: int | None = None,
) -> list[CommentedActivityResponse]:
    require_user(repo, user_id)
    capped_limit = limit or API_LIST_LIMIT
    matched: list[CommentedActivityResponse] = []
    for creator in repo.list_creators(user_id, limit=API_LIST_LIMIT):
        for activity in repo.list_creator_activities(user_id, creator["creator_id"], limit=100):
            comment_record = dict((activity.get("engagement") or {}).get("comment") or {})
            if not comment_record.get("commented"):
                continue
            matched.append(
                CommentedActivityResponse.model_validate(
                    {
                        **activity,
                        "comment_topic": str(comment_record.get("topic", "")),
                        "comment": str(comment_record.get("text", "")),
                        "commented_at": str(comment_record.get("marked_at", "")),
                    }
                )
            )
    matched.sort(key=lambda item: item.commented_at or item.fetched_at, reverse=True)
    return matched[:capped_limit]


def generate_from_activity(repo: DynamoRepository, request: GenerateFromActivityRequest) -> ThreadResponse:
    user = require_user(repo, request.user_id)
    creator = repo.get_creator(request.user_id, request.creator_id)
    if not creator:
        raise KeyError(f"Creator not found: {request.creator_id}")
    activity = repo.get_activity(request.user_id, request.creator_id, request.post_id)
    if not activity:
        raise KeyError(f"Creator post not found: {request.post_id}")

    source_text = activity["raw_text"]
    config = llm_config()
    source_style = extract_writing_style(source_text, config).model_dump()
    topic = (
        "Create a distinct LinkedIn post variation inspired by this creator post. "
        "Do not copy exact wording. Keep the topic, use similar pacing, and make it original.\n\n"
        f"Creator post:\n{source_text}"
    )
    generation_style = normalize_generation_style("Create posts from scratch")
    graph_result = run_post_generation(
        {
            "workflow_mode": "generate",
            "topic": topic,
            "writing_style": source_style,
            "generation_style": generation_style.label,
            "generation_instructions": generation_style_prompt(generation_style.label),
            "resume_profile": user.get("profile") or {},
            "messages": [{"role": "user", "content": topic}],
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "attempts": 0,
            "max_attempts": MAX_REVIEW_ATTEMPTS,
        }
    )
    post = _ensure_hashtags(graph_result.get("final_post", ""), source_text)
    timestamp = now_iso()
    thread = {
        "user_id": request.user_id,
        "thread_id": str(uuid4()),
        "topic": topic,
        "topic_source": "creator_activity",
        "generation_style": generation_style.label,
        "original_post": post,
        "current_post": post,
        "conversation": graph_result.get("messages", []),
        "provider": config.provider,
        "model": config.model,
        "source": {
            "creator_id": request.creator_id,
            "post_id": request.post_id,
            "post_url": activity.get("post_url", ""),
        },
        "writing_style_snapshot": source_style,
        "profile_snapshot": user.get("profile") or {},
        "created_at": timestamp,
        "updated_at": timestamp,
        "generated_at": timestamp,
        "modified_at": "",
        "modification_count": 0,
    }
    repo.put_thread(thread)
    return thread_response(thread)


def _normalize_profile_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "linkedin.com/in/" in text.lower():
        try:
            text = normalize_linkedin_profile_url(text)
        except ValueError:
            pass
    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return text.lower()


def _engager_profile_key(value: dict[str, Any] | str) -> str:
    if isinstance(value, str):
        return _normalize_profile_key(value)
    for key in ("profile_url", "profile_urn", "profile_key", "name"):
        normalized = _normalize_profile_key(value.get(key))
        if normalized:
            return normalized
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"unknown-{digest[:16]}"


def _user_post_id(user_id: str, post_id: str) -> str:
    return f"{user_id}#{post_id}"


def _post_url_from_id(post_id: str, post_url: str = "") -> str:
    if post_id.startswith("urn:li:activity:"):
        return f"https://www.linkedin.com/feed/update/{post_id}/"
    return post_url


def _post_id_from_raw(raw_post: dict[str, Any]) -> str:
    explicit_post_id = str(raw_post.get("post_id") or "").strip()
    if explicit_post_id:
        return explicit_post_id
    post_url = str(raw_post.get("post_url") or "").strip()
    match = LINKEDIN_ACTIVITY_RE.search(post_url)
    if match:
        return match.group(0)
    raw_text = str(raw_post.get("raw_text") or raw_post.get("post_text") or raw_post.get("text") or post_url).strip()
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return f"post-{digest[:24]}"


def _profile_url_from_user(user: dict[str, Any]) -> str:
    profile = user.get("profile") or {}
    for key in ("linkedin_url", "linkedin_profile_url", "profile_url", "linkedin"):
        value = str(profile.get(key) or "").strip()
        if "linkedin.com" in value.lower():
            return value
    links = profile.get("links")
    if isinstance(links, list):
        for item in links:
            value = str(item or "").strip()
            if "linkedin.com" in value.lower():
                return value
    return ""


def _own_post_response(record: dict[str, Any]) -> OwnPostResponse:
    return OwnPostResponse.model_validate(
        {
            "user_id": str(record.get("user_id", "")),
            "post_id": str(record.get("post_id", "")),
            "post_url": str(record.get("post_url", "")),
            "source": str(record.get("source", "platform")),
            "text": str(record.get("text", "")),
            "created_at_text": str(record.get("created_at_text", "")),
            "estimated_posted_at": str(record.get("estimated_posted_at", "")),
            "first_seen_at": str(record.get("first_seen_at", "")),
            "last_scraped_at": str(record.get("last_scraped_at", "")),
            "reaction_count": int(record.get("reaction_count") or 0),
            "comment_count": int(record.get("comment_count") or 0),
            "impression_count": int(record.get("impression_count") or 0),
            "scrape_status": str(record.get("scrape_status", "")),
            "raw_metadata": dict(record.get("raw_metadata") or {}),
            "status": str(record.get("status", "tracked")),
        }
    )


def _post_engager_response(record: dict[str, Any]) -> PostEngagerResponse:
    return PostEngagerResponse.model_validate(
        {
            "user_post_id": str(record.get("user_post_id", "")),
            "user_id": str(record.get("user_id", "")),
            "post_id": str(record.get("post_id", "")),
            "post_url": str(record.get("post_url", "")),
            "profile_key": str(record.get("profile_key", "")),
            "profile_url": str(record.get("profile_url", "")),
            "profile_urn": str(record.get("profile_urn", "")),
            "name": str(record.get("name", "")),
            "headline": str(record.get("headline", "")),
            "connection_degree": str(record.get("connection_degree", "")),
            "engagement_types": [str(item) for item in record.get("engagement_types", [])],
            "comment_text": str(record.get("comment_text", "")),
            "comment_permalink": str(record.get("comment_permalink", "")),
            "comment_urn": str(record.get("comment_urn", "")),
            "comment_text_hash": str(record.get("comment_text_hash", "")),
            "comment_timestamp_text": str(record.get("comment_timestamp_text", "")),
            "scraped_at": str(record.get("scraped_at", "")),
            "source": str(record.get("source", "playwright")),
            "raw_metadata": dict(record.get("raw_metadata") or {}),
        }
    )


def _action_log_response(record: dict[str, Any]) -> LinkedInActionLogResponse:
    return LinkedInActionLogResponse.model_validate(
        {
            "action_id": str(record.get("action_id", "")),
            "user_id": str(record.get("user_id", "")),
            "post_id": str(record.get("post_id", "")),
            "profile_url": str(record.get("profile_url", "")),
            "profile_key": str(record.get("profile_key", "")),
            "action_type": str(record.get("action_type", "")),
            "requested_text": str(record.get("requested_text", "")),
            "final_text": str(record.get("final_text", "")),
            "status": str(record.get("status", "")),
            "skip_reason": str(record.get("skip_reason", "")),
            "error_message": str(record.get("error_message", "")),
            "created_at": str(record.get("created_at", "")),
            "started_at": str(record.get("started_at", "")),
            "finished_at": str(record.get("finished_at", "")),
            "raw_metadata": dict(record.get("raw_metadata") or {}),
        }
    )


def _own_post_activity(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
) -> dict[str, Any] | None:
    return repo.get_activity(user_id, LINKEDIN_OWN_POSTS_CREATOR_ID, post_id)


def _own_post_meta(activity: dict[str, Any] | None) -> dict[str, Any]:
    if not activity:
        return {}
    return dict(activity.get(LINKEDIN_OWN_POST_META_KEY) or {})


def _own_post_record_from_activity(activity: dict[str, Any]) -> dict[str, Any]:
    meta = _own_post_meta(activity)
    return {
        **meta,
        "user_id": str(activity.get("user_id", meta.get("user_id", ""))),
        "post_id": str(activity.get("post_id", meta.get("post_id", ""))),
        "post_url": str(activity.get("post_url", meta.get("post_url", ""))),
        "text": str(meta.get("text") or activity.get("raw_text", "")),
        "created_at_text": str(meta.get("created_at_text") or activity.get("posted_at_text", "")),
        "first_seen_at": str(meta.get("first_seen_at") or activity.get("fetched_at", "")),
        "source": str(meta.get("source", "platform")),
        "estimated_posted_at": str(meta.get("estimated_posted_at", "")),
        "last_scraped_at": str(meta.get("last_scraped_at", "")),
        "reaction_count": int(meta.get("reaction_count") or 0),
        "comment_count": int(meta.get("comment_count") or 0),
        "impression_count": int(meta.get("impression_count") or 0),
        "scrape_status": str(meta.get("scrape_status", "")),
        "raw_metadata": dict(meta.get("raw_metadata") or {}),
        "status": str(meta.get("status", "tracked")),
    }


def _get_own_post_record(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
) -> dict[str, Any] | None:
    activity = _own_post_activity(repo, user_id, post_id)
    return _own_post_record_from_activity(activity) if activity else None


def _own_post_activities(
    repo: DynamoRepository,
    user_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return repo.list_creator_activities(
        user_id,
        LINKEDIN_OWN_POSTS_CREATOR_ID,
        limit or LINKEDIN_POST_EXISTING_LIMIT,
    )


def _save_own_post_record(
    repo: DynamoRepository,
    record: dict[str, Any],
) -> dict[str, Any]:
    user_id = str(record["user_id"])
    post_id = str(record["post_id"])
    timestamp = now_iso()
    existing_activity = _own_post_activity(repo, user_id, post_id) or {}
    existing_meta = _own_post_meta(existing_activity)
    meta = {**existing_meta, **record}
    text = str(meta.get("text", ""))
    content_hash = hashlib.sha256((text or post_id).encode("utf-8")).hexdigest()
    activity = {
        **existing_activity,
        "user_creator_id": f"{user_id}#{LINKEDIN_OWN_POSTS_CREATOR_ID}",
        "user_id": user_id,
        "creator_id": LINKEDIN_OWN_POSTS_CREATOR_ID,
        "post_id": post_id,
        "post_url": str(meta.get("post_url", "")),
        "raw_text": text,
        "author_name": str(meta.get("author_name", "Own LinkedIn post")),
        "posted_at_text": str(meta.get("created_at_text", "")),
        "fetched_at": str(meta.get("first_seen_at") or existing_activity.get("fetched_at") or timestamp),
        "content_hash": str(existing_activity.get("content_hash") or content_hash),
        "source": "linkedin_own_post",
        "is_new": False,
        LINKEDIN_OWN_POST_META_KEY: meta,
    }
    saved = repo.put_activity(activity)
    return _own_post_record_from_activity(saved)


def _post_engager_records(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
) -> list[dict[str, Any]]:
    activity = _own_post_activity(repo, user_id, post_id)
    meta = _own_post_meta(activity)
    engagers = meta.get("engagers") or {}
    if isinstance(engagers, dict):
        return [dict(item) for item in engagers.values() if isinstance(item, dict)]
    if isinstance(engagers, list):
        return [dict(item) for item in engagers if isinstance(item, dict)]
    return []


def _put_post_engager_record(
    repo: DynamoRepository,
    post: dict[str, Any],
    engager: dict[str, Any],
) -> dict[str, Any]:
    user_id = str(post["user_id"])
    post_id = str(post["post_id"])
    activity = _own_post_activity(repo, user_id, post_id)
    if not activity:
        raise KeyError(f"LinkedIn post not found: {post_id}")
    meta = _own_post_meta(activity)
    existing_engagers = {
        str(item.get("profile_key", "")): dict(item)
        for item in _post_engager_records(repo, user_id, post_id)
        if str(item.get("profile_key", ""))
    }
    existing_engagers[str(engager["profile_key"])] = dict(engager)
    meta["engagers"] = existing_engagers
    activity[LINKEDIN_OWN_POST_META_KEY] = meta
    repo.put_activity(activity)
    return engager


def _action_log_records(
    repo: DynamoRepository,
    user_id: str,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for activity in _own_post_activities(repo, user_id, LINKEDIN_POST_EXISTING_LIMIT):
        action_logs = _own_post_meta(activity).get("action_logs") or []
        if isinstance(action_logs, list):
            logs.extend(dict(item) for item in action_logs if isinstance(item, dict))
    return logs


def _append_action_log(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
    log: dict[str, Any],
) -> None:
    activity = _own_post_activity(repo, user_id, post_id)
    if not activity:
        raise KeyError(f"LinkedIn post not found: {post_id}")
    meta = _own_post_meta(activity)
    action_logs = list(meta.get("action_logs") or [])
    action_logs.append(log)
    meta["action_logs"] = action_logs[-LINKEDIN_POST_EXISTING_LIMIT:]
    activity[LINKEDIN_OWN_POST_META_KEY] = meta
    repo.put_activity(activity)


def _put_own_post_from_raw(
    repo: DynamoRepository,
    user_id: str,
    raw_post: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    timestamp = now_iso()
    post_id = _post_id_from_raw(raw_post)
    existing = _get_own_post_record(repo, user_id, post_id) or {}
    estimated_posted_at = _estimated_posted_at(raw_post)
    record = {
        **existing,
        "user_id": user_id,
        "post_id": post_id,
        "post_url": _post_url_from_id(post_id, str(raw_post.get("post_url") or existing.get("post_url", ""))),
        "source": source if source in {"platform", "direct"} else "direct",
        "text": str(raw_post.get("raw_text") or raw_post.get("post_text") or raw_post.get("text") or existing.get("text", "")),
        "created_at_text": str(raw_post.get("posted_at_text") or raw_post.get("created_at_text") or existing.get("created_at_text", "")),
        "estimated_posted_at": (
            estimated_posted_at.isoformat()
            if estimated_posted_at
            else str(raw_post.get("estimated_posted_at") or existing.get("estimated_posted_at", ""))
        ),
        "first_seen_at": str(existing.get("first_seen_at") or raw_post.get("fetched_at") or timestamp),
        "last_scraped_at": str(existing.get("last_scraped_at", "")),
        "reaction_count": int(raw_post.get("reaction_count") or raw_post.get("like_count") or existing.get("reaction_count") or 0),
        "comment_count": int(raw_post.get("comment_count") or existing.get("comment_count") or 0),
        "impression_count": int(raw_post.get("impression_count") or existing.get("impression_count") or 0),
        "scrape_status": str(existing.get("scrape_status", "")),
        "raw_metadata": {**dict(existing.get("raw_metadata") or {}), "last_intake_raw": raw_post},
        "status": "tracked",
    }
    return _save_own_post_record(repo, record)


def track_published_linkedin_post(
    repo: DynamoRepository,
    request: LinkedInPostPublishRequest,
) -> LinkedInPostPublishResponse:
    require_user(repo, request.user_id)
    record = _put_own_post_from_raw(
        repo,
        request.user_id,
        {
            "post_id": request.post_id,
            "post_url": request.post_url,
            "post_text": request.post_text,
            "thread_id": request.thread_id,
            "fetched_at": now_iso(),
        },
        source=request.source or "platform",
    )
    return LinkedInPostPublishResponse.model_validate(_own_post_response(record).model_dump())


def _own_post_sync_skip_reason(raw_post: dict[str, Any], window_hours: int) -> str:
    if not str(raw_post.get("raw_text", "")).strip():
        return "missing_post_text"
    posted_at = _estimated_posted_at(raw_post)
    if posted_at is None:
        posted_at_text = str(raw_post.get("posted_at_text") or "").strip()
        return f"unparseable_posted_at_text: {posted_at_text or 'empty'}"
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    if posted_at < cutoff:
        return f"outside_{window_hours}_hour_window"
    return ""


def sync_recent_linkedin_posts(
    repo: DynamoRepository,
    request: SyncRecentOwnPostsRequest,
) -> SyncRecentOwnPostsResponse:
    user = require_user(repo, request.user_id)
    profile_url = str(request.profile_url or _profile_url_from_user(user)).strip()
    if not profile_url:
        raise ValueError("profile_url is required unless the user profile contains a LinkedIn profile URL.")

    _sleep_before_playwright_launch(request.launch_delay_seconds)
    posts = fetch_recent_profile_posts(profile_url, max_posts=request.max_posts)
    if posts and isinstance(posts[0], dict) and posts[0].get("error"):
        return SyncRecentOwnPostsResponse(
            user_id=request.user_id,
            checked_count=0,
            saved_count=0,
            errors=[{"message": str(posts[0].get("message") or posts[0].get("error"))}],
        )

    saved_posts: list[OwnPostResponse] = []
    skipped_posts: list[dict[str, str]] = []
    checked_count = 0
    for post in posts:
        if not isinstance(post, dict):
            continue
        checked_count += 1
        skip_reason = _own_post_sync_skip_reason(post, request.window_hours)
        if skip_reason:
            skipped_posts.append(
                {
                    "reason": skip_reason,
                    "post_url": str(post.get("post_url") or ""),
                    "posted_at_text": str(post.get("posted_at_text") or ""),
                    "text_preview": str(post.get("raw_text") or "")[:160],
                }
            )
            continue
        record = _put_own_post_from_raw(repo, request.user_id, post, source="direct")
        saved_posts.append(_own_post_response(record))

    saved_posts.sort(key=lambda item: item.estimated_posted_at or item.first_seen_at, reverse=True)
    return SyncRecentOwnPostsResponse(
        user_id=request.user_id,
        checked_count=checked_count,
        saved_count=len(saved_posts),
        skipped_count=len(skipped_posts),
        posts=saved_posts,
        skipped_posts=skipped_posts,
    )


def list_linkedin_posts(
    repo: DynamoRepository,
    user_id: str,
    source: str | None = None,
    window_hours: int | None = 72,
    limit: int | None = None,
) -> list[OwnPostResponse]:
    require_user(repo, user_id)
    posts = [
        _own_post_response(_own_post_record_from_activity(activity))
        for activity in _own_post_activities(repo, user_id, limit or LINKEDIN_POST_EXISTING_LIMIT)
    ]
    if source:
        posts = [post for post in posts if post.source == source]
    if window_hours:
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        filtered: list[OwnPostResponse] = []
        for post in posts:
            parsed = _parse_activity_datetime(post.estimated_posted_at) or _parse_activity_datetime(post.first_seen_at)
            if parsed and parsed >= cutoff:
                filtered.append(post)
        posts = filtered
    posts.sort(key=lambda item: item.estimated_posted_at or item.first_seen_at, reverse=True)
    return posts[: limit or API_LIST_LIMIT]


def _merge_engager_record(
    repo: DynamoRepository,
    post: dict[str, Any],
    raw_engager: dict[str, Any],
) -> dict[str, Any]:
    user_id = str(post["user_id"])
    post_id = str(post["post_id"])
    profile_key = _engager_profile_key(raw_engager)
    existing = next(
        (engager for engager in _post_engager_records(repo, user_id, post_id) if engager.get("profile_key") == profile_key),
        {},
    )
    engagement_types = sorted(
        {
            str(item)
            for item in [
                *list(existing.get("engagement_types") or []),
                *list(raw_engager.get("engagement_types") or []),
            ]
            if str(item).strip()
        }
    )
    raw_metadata = dict(existing.get("raw_metadata") or {})
    raw_metadata.update(dict(raw_engager.get("raw_metadata") or {}))
    record = {
        **existing,
        "user_post_id": _user_post_id(user_id, post_id),
        "user_id": user_id,
        "post_id": post_id,
        "post_url": str(post.get("post_url", "")),
        "profile_key": profile_key,
        "profile_url": str(raw_engager.get("profile_url") or existing.get("profile_url", "")),
        "profile_urn": str(raw_engager.get("profile_urn") or existing.get("profile_urn", "")),
        "name": str(raw_engager.get("name") or existing.get("name", "")),
        "headline": str(raw_engager.get("headline") or existing.get("headline", "")),
        "connection_degree": str(raw_engager.get("connection_degree") or existing.get("connection_degree", "")),
        "engagement_types": engagement_types,
        "comment_text": str(raw_engager.get("comment_text") or existing.get("comment_text", "")),
        "comment_permalink": str(raw_engager.get("comment_permalink") or existing.get("comment_permalink", "")),
        "comment_urn": str(raw_engager.get("comment_urn") or existing.get("comment_urn", "")),
        "comment_text_hash": str(raw_engager.get("comment_text_hash") or existing.get("comment_text_hash", "")),
        "comment_timestamp_text": str(raw_engager.get("comment_timestamp_text") or existing.get("comment_timestamp_text", "")),
        "scraped_at": str(raw_engager.get("scraped_at") or now_iso()),
        "source": str(raw_engager.get("source") or existing.get("source", "playwright")),
        "raw_metadata": raw_metadata,
    }
    return _put_post_engager_record(repo, post, record)


def scrape_linkedin_post_engagement_service(
    repo: DynamoRepository,
    post_id: str,
    request: ScrapePostEngagementRequest,
) -> PostEngagementScrapeResponse:
    require_user(repo, request.user_id)
    post = _get_own_post_record(repo, request.user_id, post_id)
    if not post:
        raise KeyError(f"LinkedIn post not found: {post_id}")
    post_url = _post_url_from_id(post_id, str(post.get("post_url", "")))
    if not post_url:
        raise ValueError("The tracked post has no post_url. Track or sync a LinkedIn URL before scraping engagement.")

    _sleep_before_playwright_launch(request.launch_delay_seconds)
    result = scrape_linkedin_post_engagement(
        post_url,
        include_likes=request.include_likes,
        include_comments=request.include_comments,
    )

    saved_by_profile_key: dict[str, PostEngagerResponse] = {}
    if not result.errors:
        for raw_engager in result.engagers:
            saved_engager = _post_engager_response(_merge_engager_record(repo, post, raw_engager))
            saved_by_profile_key[saved_engager.profile_key] = saved_engager

    timestamp = now_iso()
    post["last_scraped_at"] = timestamp
    post["reaction_count"] = result.like_count
    post["comment_count"] = result.comment_count
    post["scrape_status"] = "failed" if result.errors else "scraped"
    post["raw_metadata"] = {
        **dict(post.get("raw_metadata") or {}),
        "last_engagement_scrape": {
            "scraped_at": timestamp,
            "warnings": result.warnings,
            "errors": result.errors,
            "diagnostics": result.diagnostics,
        },
    }
    _save_own_post_record(repo, post)

    return PostEngagementScrapeResponse(
        user_id=request.user_id,
        post_id=post_id,
        like_count=result.like_count,
        comment_count=result.comment_count,
        engagers_saved=len(saved_by_profile_key),
        warnings=result.warnings,
        errors=result.errors,
        engagers=list(saved_by_profile_key.values()),
    )


def list_linkedin_post_engagers(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
    engagement_type: str | None = None,
    connection_degree: str | None = None,
    limit: int | None = None,
) -> list[PostEngagerResponse]:
    require_user(repo, user_id)
    if not _get_own_post_record(repo, user_id, post_id):
        raise KeyError(f"LinkedIn post not found: {post_id}")
    engagers = [
        _post_engager_response(engager)
        for engager in _post_engager_records(repo, user_id, post_id)
    ]
    if engagement_type:
        normalized_type = engagement_type.strip().lower()
        engagers = [engager for engager in engagers if normalized_type in engager.engagement_types]
    if connection_degree:
        normalized_degree = connection_degree.strip().lower()
        engagers = [engager for engager in engagers if engager.connection_degree.strip().lower() == normalized_degree]
    engagers.sort(key=lambda item: item.scraped_at, reverse=True)
    return engagers[: limit or API_LIST_LIMIT]


def list_linkedin_action_logs(
    repo: DynamoRepository,
    user_id: str,
    post_id: str | None = None,
    action_type: str | None = None,
    limit: int | None = None,
) -> list[LinkedInActionLogResponse]:
    require_user(repo, user_id)
    logs = [_action_log_response(log) for log in _action_log_records(repo, user_id)]
    if post_id:
        logs = [log for log in logs if log.post_id == post_id]
    if action_type:
        logs = [log for log in logs if log.action_type == action_type]
    logs.sort(key=lambda item: item.created_at, reverse=True)
    return logs[: limit or API_LIST_LIMIT]


def list_linkedin_prospects(
    repo: DynamoRepository,
    user_id: str,
    engagement_type: str | None = None,
    connection_degree: str | None = None,
    search: str | None = None,
    limit: int | None = None,
) -> list[LinkedInProspectResponse]:
    require_user(repo, user_id)
    merged: dict[str, dict[str, Any]] = {}
    for activity in _own_post_activities(repo, user_id, LINKEDIN_POST_EXISTING_LIMIT):
        post = _own_post_record_from_activity(activity)
        post_id = str(post.get("post_id", ""))
        for engager in _post_engager_records(repo, user_id, post_id):
            profile_key = str(engager.get("profile_key", ""))
            if not profile_key:
                continue
            current = merged.setdefault(
                profile_key,
                {
                    "prospect_id": hashlib.sha256(profile_key.encode("utf-8")).hexdigest()[:24],
                    "user_id": user_id,
                    "profile_key": profile_key,
                    "profile_url": "",
                    "profile_urn": "",
                    "name": "",
                    "headline": "",
                    "connection_degree": "",
                    "engagement_types": set(),
                    "engagement_count": 0,
                    "source_post_ids": set(),
                    "latest_comment_text": "",
                    "last_engaged_at": "",
                },
            )
            for field in ("profile_url", "profile_urn", "name", "headline", "connection_degree"):
                if engager.get(field):
                    current[field] = str(engager[field])
            types = {str(item).lower() for item in engager.get("engagement_types", []) if str(item).strip()}
            current["engagement_types"].update(types)
            current["engagement_count"] += max(1, len(types))
            current["source_post_ids"].add(post_id)
            scraped_at = str(engager.get("scraped_at", ""))
            if scraped_at >= current["last_engaged_at"]:
                current["last_engaged_at"] = scraped_at
                if engager.get("comment_text"):
                    current["latest_comment_text"] = str(engager["comment_text"])

    latest_actions: dict[str, LinkedInActionLogResponse] = {}
    for action in sorted(_action_log_records(repo, user_id), key=lambda item: str(item.get("created_at", "")), reverse=True):
        profile_key = str(action.get("profile_key", ""))
        if profile_key and profile_key not in latest_actions:
            latest_actions[profile_key] = _action_log_response(action)

    normalized_type = str(engagement_type or "").strip().lower()
    normalized_degree = str(connection_degree or "").strip().lower()
    normalized_search = str(search or "").strip().lower()
    prospects: list[LinkedInProspectResponse] = []
    for profile_key, item in merged.items():
        engagement_types = sorted(item["engagement_types"])
        if normalized_type and normalized_type not in engagement_types:
            continue
        if normalized_degree and str(item["connection_degree"]).lower() != normalized_degree:
            continue
        haystack = " ".join(
            [str(item["name"]), str(item["headline"]), str(item["profile_url"])]
        ).lower()
        if normalized_search and normalized_search not in haystack:
            continue
        latest_action = latest_actions.get(profile_key)
        is_first_degree = str(item["connection_degree"]).strip().lower().startswith("1")
        source_post_ids = sorted(item["source_post_ids"])
        prospects.append(
            LinkedInProspectResponse(
                prospect_id=str(item["prospect_id"]),
                user_id=user_id,
                profile_key=profile_key,
                profile_url=str(item["profile_url"]),
                profile_urn=str(item["profile_urn"]),
                name=str(item["name"]),
                headline=str(item["headline"]),
                connection_degree=str(item["connection_degree"]),
                engagement_types=engagement_types,
                engagement_count=int(item["engagement_count"]),
                source_post_ids=source_post_ids,
                source_post_count=len(source_post_ids),
                latest_comment_text=str(item["latest_comment_text"]),
                last_engaged_at=str(item["last_engaged_at"]),
                latest_action_type=latest_action.action_type if latest_action else "",
                latest_action_status=latest_action.status if latest_action else "",
                can_reply="comment" in engagement_types and bool(item["latest_comment_text"]),
                can_dm=is_first_degree,
                can_connect=bool(item["profile_url"]) and not is_first_degree,
            )
        )
    prospects.sort(key=lambda item: item.last_engaged_at, reverse=True)
    return prospects[: limit or API_LIST_LIMIT]


def _target_engagers(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
    profile_urls: list[str],
    engagement_types: list[str] | None = None,
    include_explicit_missing: bool = False,
) -> list[PostEngagerResponse]:
    post = _get_own_post_record(repo, user_id, post_id)
    if not post:
        raise KeyError(f"LinkedIn post not found: {post_id}")
    selected_profiles = [
        (str(value).strip(), _engager_profile_key(value))
        for value in profile_urls
        if str(value).strip()
    ]
    selected_keys = {profile_key for _, profile_key in selected_profiles}
    allowed_types = {item.strip().lower() for item in engagement_types or [] if item.strip()}
    engagers = [
        _post_engager_response(engager)
        for engager in _post_engager_records(repo, user_id, post_id)
    ]
    if selected_keys:
        engagers = [engager for engager in engagers if engager.profile_key in selected_keys]
    if allowed_types:
        engagers = [engager for engager in engagers if allowed_types.intersection(engager.engagement_types)]
    if include_explicit_missing and selected_profiles:
        existing_keys = {engager.profile_key for engager in engagers}
        for profile_url, profile_key in selected_profiles:
            if profile_key in existing_keys:
                continue
            engagers.append(
                PostEngagerResponse(
                    user_post_id=_user_post_id(user_id, post_id),
                    user_id=user_id,
                    post_id=post_id,
                    post_url=_post_url_from_id(post_id, str(post.get("post_url", ""))),
                    profile_key=profile_key,
                    profile_url=profile_url,
                    scraped_at=now_iso(),
                    source="explicit",
                    raw_metadata={"explicit_target": True},
                )
            )
            existing_keys.add(profile_key)
    return engagers


def _is_first_degree(connection_degree: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", connection_degree.lower())
    return normalized in {"1", "1st", "first"}


def _has_prior_action(
    repo: DynamoRepository,
    user_id: str,
    profile_key: str,
    action_type: str,
    post_id: str | None = None,
) -> bool:
    for log in _action_log_records(repo, user_id):
        if str(log.get("action_type")) != action_type:
            continue
        if str(log.get("profile_key")) != profile_key:
            continue
        if post_id and str(log.get("post_id")) != post_id:
            continue
        if str(log.get("status")) in {"queued", "running", "sent"}:
            return True
    return False


def _write_action_log(
    repo: DynamoRepository,
    user_id: str,
    post_id: str,
    engager: PostEngagerResponse,
    action_type: str,
    requested_text: str,
    status: str,
    skip_reason: str = "",
    error_message: str = "",
    final_text: str = "",
    started_at: str = "",
    raw_metadata: dict[str, Any] | None = None,
) -> LinkedInActionResult:
    timestamp = now_iso()
    key_fragment = hashlib.sha256(f"{engager.profile_key}#{action_type}#{timestamp}".encode("utf-8")).hexdigest()[:12]
    action_id = f"{timestamp}#{action_type}#{key_fragment}"
    log = {
        "action_id": action_id,
        "user_id": user_id,
        "post_id": post_id,
        "profile_url": engager.profile_url,
        "profile_key": engager.profile_key,
        "action_type": action_type,
        "requested_text": requested_text,
        "final_text": final_text,
        "status": status,
        "skip_reason": skip_reason,
        "error_message": error_message,
        "created_at": timestamp,
        "started_at": started_at,
        "finished_at": timestamp if status in {"sent", "skipped", "failed"} else "",
        "raw_metadata": raw_metadata or {},
    }
    _append_action_log(repo, user_id, post_id, log)
    return LinkedInActionResult(
        profile_url=engager.profile_url,
        profile_key=engager.profile_key,
        action_id=action_id,
        action_type=action_type,
        status=status,
        skip_reason=skip_reason,
        error_message=error_message,
        final_text=final_text,
    )


def send_comment_replies(
    repo: DynamoRepository,
    request: CommentReplyActionRequest,
) -> LinkedInActionBatchResponse:
    require_user(repo, request.user_id)
    post = _get_own_post_record(repo, request.user_id, request.post_id)
    if not post:
        raise KeyError(f"LinkedIn post not found: {request.post_id}")
    targets = _target_engagers(repo, request.user_id, request.post_id, request.profile_urls)
    results: list[LinkedInActionResult] = []

    for engager in targets:
        if "comment" not in engager.engagement_types:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "comment_reply",
                    request.reply_text,
                    "skipped",
                    skip_reason="not_a_commenter",
                )
            )
            continue
        if _has_prior_action(repo, request.user_id, engager.profile_key, "comment_reply", post_id=request.post_id):
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "comment_reply",
                    request.reply_text,
                    "skipped",
                    skip_reason="duplicate_comment_reply",
                )
            )
            continue
        if request.dry_run:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "comment_reply",
                    request.reply_text,
                    "skipped",
                    skip_reason="dry_run",
                    final_text=request.reply_text,
                )
            )
            continue

        _sleep_before_playwright_launch(request.launch_delay_seconds)
        started_at = now_iso()
        action_result = reply_to_comment(
            str(post.get("post_url", "")),
            {
                "comment_permalink": engager.comment_permalink,
                "comment_urn": engager.comment_urn,
                "comment_text": engager.comment_text,
                "name": engager.name,
            },
            request.reply_text,
        )
        results.append(
            _write_action_log(
                repo,
                request.user_id,
                request.post_id,
                engager,
                "comment_reply",
                request.reply_text,
                "sent" if action_result.ok else "failed",
                error_message=action_result.error_message,
                final_text=action_result.final_text or request.reply_text,
                started_at=started_at,
                raw_metadata=action_result.raw_metadata,
            )
        )

    return LinkedInActionBatchResponse(
        user_id=request.user_id,
        post_id=request.post_id,
        action_type="comment_reply",
        results=results,
    )


def send_connection_requests(
    repo: DynamoRepository,
    request: ConnectionRequestActionRequest,
) -> LinkedInActionBatchResponse:
    require_user(repo, request.user_id)
    targets = _target_engagers(
        repo,
        request.user_id,
        request.post_id,
        request.profile_urls,
        request.engagement_types,
    )
    results: list[LinkedInActionResult] = []

    for engager in targets:
        if not engager.profile_url:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "connection_request",
                    request.note,
                    "skipped",
                    skip_reason="missing_profile_url",
                )
            )
            continue
        if _is_first_degree(engager.connection_degree):
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "connection_request",
                    request.note,
                    "skipped",
                    skip_reason="already_first_degree",
                )
            )
            continue
        if _has_prior_action(repo, request.user_id, engager.profile_key, "connection_request"):
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "connection_request",
                    request.note,
                    "skipped",
                    skip_reason="duplicate_connection_request",
                )
            )
            continue
        if request.dry_run:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "connection_request",
                    request.note,
                    "skipped",
                    skip_reason="dry_run",
                    final_text=request.note,
                )
            )
            continue

        _sleep_before_playwright_launch(request.launch_delay_seconds)
        started_at = now_iso()
        action_result = send_connection_request(engager.profile_url, request.note)
        results.append(
            _write_action_log(
                repo,
                request.user_id,
                request.post_id,
                engager,
                "connection_request",
                request.note,
                "sent" if action_result.ok else "failed",
                error_message=action_result.error_message,
                final_text=action_result.final_text or request.note,
                started_at=started_at,
                raw_metadata=action_result.raw_metadata,
            )
        )

    return LinkedInActionBatchResponse(
        user_id=request.user_id,
        post_id=request.post_id,
        action_type="connection_request",
        results=results,
    )


def send_dms(
    repo: DynamoRepository,
    request: DmActionRequest,
) -> LinkedInActionBatchResponse:
    require_user(repo, request.user_id)
    targets = _target_engagers(
        repo,
        request.user_id,
        request.post_id,
        request.profile_urls,
        include_explicit_missing=True,
    )
    results: list[LinkedInActionResult] = []

    for engager in targets:
        if not engager.profile_url:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "dm",
                    request.message,
                    "skipped",
                    skip_reason="missing_profile_url",
                )
            )
            continue
        explicit_target = bool(engager.raw_metadata.get("explicit_target"))
        if not explicit_target and not _is_first_degree(engager.connection_degree):
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "dm",
                    request.message,
                    "skipped",
                    skip_reason="not_first_degree",
                )
            )
            continue
        if _has_prior_action(repo, request.user_id, engager.profile_key, "dm"):
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "dm",
                    request.message,
                    "skipped",
                    skip_reason="duplicate_dm",
                )
            )
            continue
        if request.dry_run:
            results.append(
                _write_action_log(
                    repo,
                    request.user_id,
                    request.post_id,
                    engager,
                    "dm",
                    request.message,
                    "skipped",
                    skip_reason="dry_run",
                    final_text=request.message,
                )
            )
            continue

        _sleep_before_playwright_launch(request.launch_delay_seconds)
        started_at = now_iso()
        action_result = send_dm(engager.profile_url, request.message)
        results.append(
            _write_action_log(
                repo,
                request.user_id,
                request.post_id,
                engager,
                "dm",
                request.message,
                "sent" if action_result.ok else "failed",
                error_message=action_result.error_message,
                final_text=action_result.final_text or request.message,
                started_at=started_at,
                raw_metadata=action_result.raw_metadata,
            )
        )

    return LinkedInActionBatchResponse(
        user_id=request.user_id,
        post_id=request.post_id,
        action_type="dm",
        results=results,
    )
