from __future__ import annotations

import hashlib
import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.config import (
    EXTENSION_SCRAPE_TASK_LEASE_SECONDS,
    EXTENSION_SCRAPE_TASK_TIMEOUT_SECONDS,
    SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS,
    SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS,
    SCRAPE_LONG_BREAK_EVERY_CREATORS,
    SCRAPE_LONG_BREAK_MAX_SECONDS,
    SCRAPE_LONG_BREAK_MIN_SECONDS,
)
from app.db.dynamodb import get_repository

_ACTIVITY_RE = re.compile(r"urn:li:activity:\d+")
def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _activity_urn(*values: Any) -> str:
    for value in values:
        match = _ACTIVITY_RE.search(str(value or ""))
        if match:
            return match.group(0)
    return ""


def normalize_extension_posts(data: Any, max_posts: int) -> list[dict[str, Any]]:
    candidates = data if isinstance(data, list) else []
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw_text = _clean_text(candidate.get("raw_text"))
        if len(raw_text) < 30:
            continue
        repost_text = _clean_text(candidate.get("repost_text"))
        content_text = "\n".join(part for part in (repost_text, raw_text) if part)
        content_hash = hashlib.sha256(content_text.lower().encode("utf-8")).hexdigest()
        activity_urn = _activity_urn(
            candidate.get("data_urn"),
            candidate.get("post_url"),
            raw_text,
        )
        post_id = activity_urn or content_hash
        if post_id in seen:
            continue
        seen.add(post_id)
        post_url = str(candidate.get("post_url", "")).strip()
        if activity_urn:
            post_url = f"https://www.linkedin.com/feed/update/{activity_urn}/"
        is_repost = bool(candidate.get("is_repost"))
        posts.append(
            {
                "post_id": post_id,
                "post_url": post_url,
                "raw_text": raw_text,
                "author_name": _clean_text(candidate.get("author_name")),
                "posted_at_text": _clean_text(candidate.get("posted_at_text")),
                "is_repost": is_repost,
                "repost_text": repost_text if is_repost else "",
                "original_post_text": _clean_text(candidate.get("original_post_text")) if is_repost else "",
                "original_author_name": _clean_text(candidate.get("original_author_name")) if is_repost else "",
                "original_author_url": str(candidate.get("original_author_url", "")).strip() if is_repost else "",
                "fetched_at": _now(),
                "content_hash": content_hash,
                "source": "extension",
            }
        )
        if len(posts) >= max_posts:
            break
    return posts


def heartbeat_extension(user_id: str, extension_id: str, version: str = "") -> None:
    get_repository().put_extension_client(user_id, {
        "user_id": user_id,
        "extension_id": extension_id,
        "version": version,
        "last_seen_at": _now(),
        "last_seen_epoch": time.time(),
    })


def claim_extension_task(user_id: str, extension_id: str, version: str = "") -> dict[str, Any] | None:
    heartbeat_extension(user_id, extension_id, version)
    repo = get_repository()
    now = time.time()
    tasks = sorted(
        repo.list_extension_tasks(user_id),
        key=lambda item: (
            str(item.get("created_at", "")),
            int(item.get("ordinal") or 0),
            str(item.get("task_id", "")),
        ),
    )
    for task in tasks:
        status = str(task.get("status", ""))
        if status == "claimed" and float(task.get("lease_expires_epoch") or 0) <= now:
            status = "queued"
        if status != "queued":
            continue
        task.update({
            "status": "claimed",
            "extension_id": extension_id,
            "claimed_at": _now(),
            "lease_expires_epoch": now + EXTENSION_SCRAPE_TASK_LEASE_SECONDS,
            "attempts": int(task.get("attempts") or 0) + 1,
        })
        repo.put_extension_task(user_id, task)
        return {key: value for key, value in task.items() if key not in {"result", "error"}}
    return None


def renew_extension_task_lease(task_id: str, user_id: str, extension_id: str) -> dict[str, Any]:
    repo = get_repository()
    task = repo.get_extension_task(user_id, task_id)
    if not task:
        raise KeyError(f"Extension scrape task not found: {task_id}")
    if str(task.get("status", "")) != "claimed":
        raise ValueError("This extension scrape task is not active.")
    if str(task.get("extension_id", "")) != extension_id:
        raise ValueError("This extension scrape task is claimed by another extension.")
    task["lease_expires_epoch"] = time.time() + EXTENSION_SCRAPE_TASK_LEASE_SECONDS
    task["lease_renewed_at"] = _now()
    repo.put_extension_task(user_id, task)
    heartbeat_extension(user_id, extension_id)
    return task


def complete_extension_task(
    task_id: str,
    user_id: str,
    extension_id: str,
    status: str,
    data: Any = None,
    error: str = "",
) -> dict[str, Any]:
    repo = get_repository()
    task = repo.get_extension_task(user_id, task_id)
    if not task:
        raise KeyError(f"Extension scrape task not found: {task_id}")
    claimed_by = str(task.get("extension_id", ""))
    if claimed_by and claimed_by != extension_id:
        raise ValueError("This extension scrape task is claimed by another extension.")
    task.update({
        "status": "succeeded" if status == "succeeded" else "failed",
        "result": data,
        "error": error,
        "completed_at": _now(),
    })
    repo.put_extension_task(user_id, task)
    heartbeat_extension(user_id, extension_id)
    return task


def enqueue_extension_scrape_tasks(
    *,
    job_id: str,
    job_type: str,
    user_id: str,
    creators: list[dict[str, Any]],
    max_posts: int = 0,
    window_hours: int = 24,
) -> list[dict[str, Any]]:
    scrape_type = "posts" if job_type == "creator_posts" else "profile"
    total = len(creators)
    tasks: list[dict[str, Any]] = []
    repo = get_repository()
    for ordinal, creator in enumerate(creators, start=1):
        task = {
            "task_id": f"{job_id}-{ordinal:05d}",
            "job_id": job_id,
            "job_type": job_type,
            "scrape_type": scrape_type,
            "user_id": user_id,
            "creator_id": str(creator["creator_id"]),
            "profile_url": str(creator["profile_url"]),
            "max_posts": max_posts,
            "window_hours": window_hours,
            "ordinal": ordinal,
            "total_creators": total,
            "status": "queued",
            "extension_id": "",
            "created_at": _now(),
            "lease_expires_epoch": 0.0,
            "attempts": 0,
            "result": None,
            "error": "",
            "delay_min_seconds": SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS,
            "delay_max_seconds": SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS,
            "long_break_every_creators": SCRAPE_LONG_BREAK_EVERY_CREATORS,
            "long_break_min_seconds": SCRAPE_LONG_BREAK_MIN_SECONDS,
            "long_break_max_seconds": SCRAPE_LONG_BREAK_MAX_SECONDS,
        }
        repo.put_extension_task(user_id, task)
        tasks.append(task)
    return tasks


def request_extension_scrape(
    *,
    scrape_type: str,
    user_id: str,
    creator_id: str,
    profile_url: str,
    max_posts: int = 0,
) -> Any:
    if scrape_type not in {"posts", "profile"}:
        raise ValueError(f"Unsupported extension scrape type: {scrape_type}")
    task_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}-{scrape_type}-{uuid4()}"
    task = {
        "task_id": task_id,
        "scrape_type": scrape_type,
        "user_id": user_id,
        "creator_id": creator_id,
        "profile_url": profile_url,
        "max_posts": max_posts,
        "status": "queued",
        "extension_id": "",
        "created_at": _now(),
        "lease_expires_epoch": 0.0,
        "result": None,
        "error": "",
    }
    repo = get_repository()
    repo.put_extension_task(user_id, task)
    deadline = time.monotonic() + EXTENSION_SCRAPE_TASK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = repo.get_extension_task(user_id, task_id) or task
        if current.get("status") in {"succeeded", "failed"}:
            task = current
            break
        time.sleep(2)
    else:
        task.update({
            "status": "failed",
            "error": "Chrome extension did not complete the scrape task before the timeout. Confirm it is enabled and connected.",
        })
        repo.put_extension_task(user_id, task)
    status = str(task.get("status", "failed"))
    data = task.get("result")
    error = str(task.get("error", ""))
    repo.delete_extension_task(user_id, task_id)

    if status != "succeeded":
        raise RuntimeError(error or "Chrome extension scrape failed.")
    if scrape_type == "posts":
        return normalize_extension_posts(data, max_posts=max(1, max_posts))
    if not isinstance(data, dict):
        raise RuntimeError("Chrome extension returned invalid profile details.")
    normalized = dict(data)
    normalized["source"] = "extension"
    normalized.setdefault("fetched_at", _now())
    return normalized


def extension_status(user_id: str) -> dict[str, Any]:
    repo = get_repository()
    latest = max(repo.list_extension_clients(user_id), key=lambda item: float(item.get("last_seen_epoch") or 0), default={})
    tasks = repo.list_extension_tasks(user_id)
    last_seen = float(latest.get("last_seen_epoch") or 0)
    return {
        "connected": bool(last_seen and time.time() - last_seen <= 45),
        "extension_id": str(latest.get("extension_id", "")),
        "version": str(latest.get("version", "")),
        "last_seen_at": str(latest.get("last_seen_at", "")),
        "queued_tasks": sum(1 for task in tasks if task.get("status") == "queued"),
        "active_tasks": sum(1 for task in tasks if task.get("status") == "claimed"),
    }
