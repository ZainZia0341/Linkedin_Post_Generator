from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from app.api.schemas import (
    ActivityResponse,
    BrainstormRequest,
    BrainstormResponse,
    CommentResponse,
    CommentedActivityResponse,
    CreatorResponse,
    GenerateCommentRequest,
    GenerateFromActivityRequest,
    GeneratePostRequest,
    MarkCommentedRequest,
    ModifyPostRequest,
    ScrapeCreatorsRequest,
    ScrapeCreatorsResponse,
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
    SCRAPE_MAX_WORKERS,
)
from app.creator_tracking import get_profile_id, normalize_linkedin_profile_url
from app.db.dynamodb import DynamoRepository
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.linkedin_playwright_scraper import fetch_recent_profile_posts
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import GeneratedComment
from app.llms.prompts import COMMENT_GENERATION_SYSTEM_PROMPT, COMMENT_GENERATION_USER_PROMPT
from app.post_generation_styles import (
    DEFAULT_GENERATION_STYLE,
    generation_style_labels,
    generation_style_prompt,
    normalize_generation_style,
)
from app.post_formatting import HASHTAG_RE, format_linkedin_post
from app.writing_style_extract import extract_writing_style, get_builtin_writing_style

POST_CREATION_ACTIONS = generation_style_labels()
COMMENT_TOPICS = ["Add Value", "Congratulate", "Agree", "Disagree", "Challenge", "Expert Insight"]

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


def _ensure_hashtags(post: str, topic: str) -> str:
    formatted = format_linkedin_post(post)
    if HASHTAG_RE.search(formatted):
        return formatted
    words = [word.strip("#.,:;!?").title() for word in topic.split() if len(word.strip("#.,:;!?")) > 3]
    tags = ["#LinkedIn", "#CareerGrowth"]
    for word in words:
        tag = f"#{''.join(ch for ch in word if ch.isalnum())}"
        if len(tag) > 1 and tag not in tags:
            tags.append(tag)
        if len(tags) == 4:
            break
    return format_linkedin_post(formatted + "\n\n" + " ".join(tags))


def generate_post(repo: DynamoRepository, request: GeneratePostRequest) -> ThreadResponse:
    user = require_user(repo, request.user_id)
    config = llm_config()
    style = _resolve_style(user, None)
    generation_style = normalize_generation_style(request.generation_style or DEFAULT_GENERATION_STYLE)
    profile = user.get("profile") or {}

    graph_result = run_post_generation(
        {
            "workflow_mode": "generate",
            "topic": request.idea,
            "writing_style": style,
            "generation_style": generation_style.label,
            "generation_instructions": generation_style_prompt(generation_style.label),
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
        "generation_style": generation_style.label,
        "original_post": post,
        "current_post": post,
        "conversation": graph_result.get("messages", []),
        "provider": config.provider,
        "model": config.model,
        "source": {},
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
    record = {
        "user_id": user_id,
        "creator_id": creator_id,
        "profile_url": normalized_url,
        "display_name": creator_id,
        "added_at": existing.get("added_at", timestamp) if existing else timestamp,
        "updated_at": timestamp,
        "last_checked_at": existing.get("last_checked_at") if existing else None,
        "seen_count": existing.get("seen_count", 0) if existing else 0,
        "new_count": existing.get("new_count", 0) if existing else 0,
    }
    return CreatorResponse.model_validate(repo.put_creator(record))


def creator_response(creator: dict[str, Any]) -> CreatorResponse:
    return CreatorResponse.model_validate(creator)


def _activity_response(activity: dict[str, Any]) -> ActivityResponse:
    return ActivityResponse.model_validate(activity)


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

    errors: list[dict[str, str]] = []
    new_activities: list[ActivityResponse] = []

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        posts = fetch_recent_profile_posts(creator["profile_url"], max_posts=request.max_posts)
        return creator, posts

    max_workers = 1 if LINKEDIN_AUTOMATION_MODE.strip().lower() == "burner" else max(1, SCRAPE_MAX_WORKERS)
    if max_workers == 1 and len(creators) > 1:
        print("Running creator scrapes sequentially because the active LinkedIn mode uses a shared browser profile.")

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

    return ScrapeCreatorsResponse(
        user_id=request.user_id,
        checked_creator_ids=[creator["creator_id"] for creator in creators],
        new_activities=new_activities,
        errors=errors,
    )


def list_all_activities(repo: DynamoRepository, user_id: str, limit: int | None = None) -> list[ActivityResponse]:
    require_user(repo, user_id)
    activities: list[ActivityResponse] = []
    for creator in repo.list_creators(user_id, limit=limit or API_LIST_LIMIT):
        activities.extend(
            _activity_response(activity)
            for activity in repo.list_creator_activities(user_id, creator["creator_id"], limit or API_LIST_LIMIT)
        )
    return activities[: limit or API_LIST_LIMIT]


def _normalize_comment_topic(comment_topic: str | None) -> str:
    cleaned = (comment_topic or "").strip()
    if not cleaned:
        return COMMENT_TOPICS[0]
    for topic in COMMENT_TOPICS:
        if cleaned.lower() == topic.lower():
            return topic
    return cleaned


def _format_comment(comment: str) -> str:
    cleaned = re.sub(r"\s+", " ", comment or "").strip()
    cleaned = cleaned.replace("#", "").strip()
    if not cleaned:
        return "This is a useful angle. The practical takeaway is worth testing in a real workflow."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    compact = " ".join(sentence for sentence in sentences[:2] if sentence).strip()
    words = compact.split()
    if len(words) > 55:
        compact = " ".join(words[:55]).rstrip(".,;:") + "."
    return compact


def _comment_fallback(comment_topic: str, creator_post: str) -> GeneratedComment:
    snippet = " ".join(creator_post.split()[:18])
    if comment_topic == "Congratulate":
        comment = "Congrats on sharing this. The practical breakdown makes the idea much easier to act on."
    elif comment_topic == "Agree":
        comment = "Agreed. The strongest point here is that the workflow matters as much as the tool itself."
    elif comment_topic == "Disagree":
        comment = "I see the point, though I would be careful about treating this as universal. The right answer still depends on the workflow and constraints."
    elif comment_topic == "Challenge":
        comment = "Good point. The question I would ask is: what is the first signal that this approach is actually working in production?"
    elif comment_topic == "Expert Insight":
        comment = "The underrated part is the operating model around this. Without review loops and clear ownership, even strong tools create noisy outputs."
    else:
        comment = f"Useful angle. One thing I would add: connect this back to the smallest repeatable workflow, not just the headline idea. Context: {snippet}"
    return GeneratedComment(comment=_format_comment(comment), rationale="Deterministic fallback comment.")


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
        comment_topic=str(comment_record.get("topic", "")),
        comment=str(comment_record.get("text", "")),
        provider=str(comment_record.get("provider", "")),
        model=str(comment_record.get("model", "")),
        generated_at=str(comment_record.get("generated_at", "")),
        commented=bool(comment_record.get("commented", False)),
    )


def generate_comment(repo: DynamoRepository, request: GenerateCommentRequest) -> CommentResponse:
    user, _, activity = _require_creator_activity(repo, request.user_id, request.creator_id, request.post_id)
    config = llm_config()
    comment_topic = _normalize_comment_topic(request.comment_topic)
    creator_post = str(activity.get("raw_text", ""))
    generated = invoke_structured(
        config=config,
        schema=GeneratedComment,
        system_prompt=COMMENT_GENERATION_SYSTEM_PROMPT,
        user_prompt=COMMENT_GENERATION_USER_PROMPT.format(
            creator_post=creator_post[:5000],
            comment_topic=comment_topic,
            resume_profile=json.dumps(user.get("profile") or {}, ensure_ascii=True, indent=2),
        ),
        fallback_factory=lambda: _comment_fallback(comment_topic, creator_post),
    )
    timestamp = now_iso()
    engagement = dict(activity.get("engagement") or {})
    previous_comment = dict(engagement.get("comment") or {})
    comment_record = {
        **previous_comment,
        "topic": comment_topic,
        "text": _format_comment(generated.comment),
        "generated_at": timestamp,
        "provider": config.provider,
        "model": config.model,
    }
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
        comment_record["text"] = _format_comment(request.comment_text)
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
