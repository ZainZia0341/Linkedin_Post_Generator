from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import re
import time
from typing import Any
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
    GenerateCommentRequest,
    GenerateFromActivityRequest,
    GeneratePostRequest,
    MarkCommentedRequest,
    ModifyPostRequest,
    RecentActivitiesResponse,
    RecentScrapeCreatorsRequest,
    RecentScrapeCreatorsResponse,
    ScrapeCreatorProfilesRequest,
    ScrapeCreatorProfilesResponse,
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
from app.linkedin_playwright_scraper import fetch_profile_details, fetch_recent_profile_posts
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
LINKEDIN_URL_RE = re.compile(r"(?<![a-z0-9.-])(?:https?://)?(?:www\.)?linkedin\.com(?:/[^\s<>'\"]*)?", flags=re.I)
CREATOR_IMPORT_EXISTING_LIMIT = 1000
RECENTLY_ADDED_WINDOW_DAYS = 7
SCRAPING_STALE_AFTER_HOURS = 24
RECENT_ACTIVITY_RETENTION_DAYS = 3
DEFAULT_PLAYWRIGHT_LAUNCH_DELAY_SECONDS = 3

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
) -> ScrapeCreatorProfilesResponse:
    require_user(repo, request.user_id)
    creators = repo.list_creators(request.user_id, limit=CREATOR_IMPORT_EXISTING_LIMIT)
    if request.creator_ids:
        creator_id_set = set(request.creator_ids)
        creators = [creator for creator in creators if creator["creator_id"] in creator_id_set]

    errors: list[dict[str, str]] = []
    profiles: list[CreatorProfileDetailsResponse] = []

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        _sleep_before_playwright_launch(request.launch_delay_seconds)
        return creator, fetch_profile_details(creator["profile_url"])

    max_workers = 1 if LINKEDIN_AUTOMATION_MODE.strip().lower() == "burner" else max(1, SCRAPE_MAX_WORKERS)
    if max_workers == 1 and len(creators) > 1:
        print("Running creator profile scrapes sequentially because the active LinkedIn mode uses a shared browser profile.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(scrape_one, creator): creator for creator in creators}
        for future in as_completed(future_map):
            creator = future_map[future]
            timestamp = now_iso()
            try:
                _, raw_details = future.result()
            except Exception as exc:
                errors.append({"creator_id": creator["creator_id"], "message": str(exc)})
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
                continue

            details = _normalize_profile_details(raw_details)
            creator["profile_details"] = details
            creator["profile_details_checked_at"] = details.get("fetched_at") or timestamp
            if details.get("name"):
                creator["display_name"] = details["name"]
            creator["updated_at"] = timestamp
            saved_creator = repo.put_creator(creator)
            profiles.append(_creator_profile_details_response(saved_creator))

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
        _sleep_before_playwright_launch(request.launch_delay_seconds)
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


def scrape_creators_recent_24h(
    repo: DynamoRepository,
    request: RecentScrapeCreatorsRequest,
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

    def scrape_one(creator: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        _sleep_before_playwright_launch(request.launch_delay_seconds)
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

            creator["last_checked_at"] = timestamp
            creator["seen_count"] = len(repo.list_creator_activities(request.user_id, creator["creator_id"], API_LIST_LIMIT))
            creator["new_count"] = creator_new_count
            creator["updated_at"] = timestamp
            repo.put_creator(creator)

    return RecentScrapeCreatorsResponse(
        user_id=request.user_id,
        checked_creator_ids=[creator["creator_id"] for creator in creators],
        window_hours=request.window_hours,
        activities=activities,
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
    return added_at >= now - timedelta(days=RECENTLY_ADDED_WINDOW_DAYS)


def build_dashboard_stats(
    creators: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    activities: list[ActivityResponse | dict[str, Any]],
) -> DashboardStatsResponse:
    now = datetime.now(UTC)
    activity_dicts = [_activity_to_dict(activity) for activity in activities]
    return DashboardStatsResponse(
        creator_count=len(creators),
        thread_count=len(threads),
        activity_count=len(activity_dicts),
        new_posts_today_count=sum(1 for activity in activity_dicts if _is_post_inside_window(activity, 24)),
        new_posts_from_last_scrape_count=sum(int(creator.get("new_count") or 0) for creator in creators),
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
