from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import (
    LINKEDIN_CHECK_MAX_POSTS,
    LINKEDIN_DEFAULT_TRACK_URL,
    TRACKED_PROFILE_DIR,
    TRACKED_PROFILE_INDEX_PATH,
    ensure_local_db,
)
from app.linkedin_playwright_scraper import fetch_recent_profile_posts


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Tracked creator file was invalid JSON, using default: {path}")
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _profile_path(profile_id: str) -> Path:
    return TRACKED_PROFILE_DIR / f"{profile_id}.json"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _content_hash(text: str) -> str:
    normalized = _clean_text(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_linkedin_profile_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        value = LINKEDIN_DEFAULT_TRACK_URL
    if not re.match(r"^https?://", value, flags=re.I):
        value = f"https://{value.lstrip('/')}"

    parsed = urlparse(value)
    netloc = parsed.netloc.lower()
    if "linkedin.com" not in netloc:
        raise ValueError("Only LinkedIn profile URLs can be tracked.")

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) >= 2 and segments[0].lower() in {"in", "company", "pub"}:
        path = "/".join(segments[:2])
    elif segments:
        path = "/".join(segments[:1])
    else:
        raise ValueError("LinkedIn profile URL must include a profile path.")

    return f"https://www.linkedin.com/{path}/"


def get_profile_id(profile_url: str) -> str:
    normalized = normalize_linkedin_profile_url(profile_url)
    segments = [segment for segment in urlparse(normalized).path.split("/") if segment]
    slug = segments[-1] if segments else normalized
    profile_id = re.sub(r"[^a-z0-9_-]+", "-", slug.lower()).strip("-")
    if profile_id:
        return profile_id
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _display_name(profile_url: str) -> str:
    segments = [segment for segment in urlparse(profile_url).path.split("/") if segment]
    return segments[-1] if segments else profile_url


def _empty_profile(profile_url: str) -> dict[str, Any]:
    normalized = normalize_linkedin_profile_url(profile_url)
    timestamp = _now()
    return {
        "profile_id": get_profile_id(normalized),
        "profile_url": normalized,
        "display_name": _display_name(normalized),
        "added_at": timestamp,
        "last_checked_at": None,
        "last_error": "",
        "seen_posts": [],
        "used_post_ids": [],
    }


def _unused_posts_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    used_ids = set(profile.get("used_post_ids", []))
    posts = []
    for post in profile.get("seen_posts", []):
        post_id = post.get("post_id") or post.get("content_hash")
        if post_id and post_id not in used_ids:
            posts.append(post)
    return sorted(posts, key=lambda post: post.get("fetched_at") or "", reverse=True)


def _profile_with_counts(profile: dict[str, Any]) -> dict[str, Any]:
    profile = dict(profile)
    seen_posts = profile.get("seen_posts", [])
    used_post_ids = profile.get("used_post_ids", [])
    profile["seen_count"] = len(seen_posts) if isinstance(seen_posts, list) else 0
    profile["used_count"] = len(used_post_ids) if isinstance(used_post_ids, list) else 0
    profile["unused_count"] = len(_unused_posts_from_profile(profile))
    return profile


def _index_record(profile: dict[str, Any]) -> dict[str, Any]:
    counted = _profile_with_counts(profile)
    return {
        "profile_id": counted.get("profile_id", ""),
        "profile_url": counted.get("profile_url", ""),
        "display_name": counted.get("display_name", ""),
        "added_at": counted.get("added_at", ""),
        "last_checked_at": counted.get("last_checked_at"),
        "seen_count": counted.get("seen_count", 0),
        "used_count": counted.get("used_count", 0),
        "unused_count": counted.get("unused_count", 0),
    }


def _load_index() -> dict[str, Any]:
    ensure_local_db()
    index = _read_json(TRACKED_PROFILE_INDEX_PATH, {"profiles": []})
    if not isinstance(index, dict):
        return {"profiles": []}
    profiles = index.get("profiles", [])
    index["profiles"] = profiles if isinstance(profiles, list) else []
    return index


def _save_index(index: dict[str, Any]) -> None:
    ensure_local_db()
    _write_json(TRACKED_PROFILE_INDEX_PATH, index)


def _update_index(profile: dict[str, Any]) -> None:
    index = _load_index()
    record = _index_record(profile)
    profiles = []
    replaced = False
    for row in index.get("profiles", []):
        if row.get("profile_id") == record["profile_id"]:
            profiles.append(record)
            replaced = True
        else:
            profiles.append(row)
    if not replaced:
        profiles.append(record)
    index["profiles"] = sorted(profiles, key=lambda row: row.get("added_at") or "")
    _save_index(index)


def seed_default_profile_if_empty() -> None:
    if not list_tracked_profiles():
        add_tracked_profile(LINKEDIN_DEFAULT_TRACK_URL)
        print("Seeded default tracked LinkedIn creator.")


def add_tracked_profile(url: str | None) -> dict[str, Any]:
    profile_url = normalize_linkedin_profile_url(url or LINKEDIN_DEFAULT_TRACK_URL)
    profile_id = get_profile_id(profile_url)
    path = _profile_path(profile_id)
    if path.exists():
        print(f"Tracked creator already exists: {profile_id}")
        return load_tracked_profile(profile_id)

    profile = _empty_profile(profile_url)
    save_tracked_profile(profile)
    print(f"Added tracked LinkedIn creator: {profile_id}")
    return _profile_with_counts(profile)


def list_tracked_profiles() -> list[dict[str, Any]]:
    index = _load_index()
    return sorted(index.get("profiles", []), key=lambda row: row.get("display_name") or "")


def load_tracked_profile(profile_id: str) -> dict[str, Any]:
    ensure_local_db()
    path = _profile_path(profile_id)
    profile = _read_json(path, None)
    if isinstance(profile, dict):
        return _profile_with_counts(profile)

    for row in list_tracked_profiles():
        if row.get("profile_id") == profile_id:
            profile = _empty_profile(row.get("profile_url", LINKEDIN_DEFAULT_TRACK_URL))
            profile["profile_id"] = profile_id
            profile["display_name"] = row.get("display_name", profile["display_name"])
            return _profile_with_counts(profile)
    raise ValueError(f"Tracked profile not found: {profile_id}")


def save_tracked_profile(profile: dict[str, Any]) -> dict[str, Any]:
    ensure_local_db()
    profile = dict(profile)
    profile["profile_url"] = normalize_linkedin_profile_url(profile.get("profile_url", ""))
    profile["profile_id"] = profile.get("profile_id") or get_profile_id(profile["profile_url"])
    profile["display_name"] = profile.get("display_name") or _display_name(profile["profile_url"])
    profile.setdefault("added_at", _now())
    profile.setdefault("last_checked_at", None)
    profile.setdefault("last_error", "")
    profile.setdefault("seen_posts", [])
    profile.setdefault("used_post_ids", [])
    counted = _profile_with_counts(profile)
    _write_json(_profile_path(counted["profile_id"]), counted)
    _update_index(counted)
    print(f"Saved tracked creator profile: {counted['profile_id']}")
    return counted


def _normalize_post_record(post: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    raw_text = _clean_text(str(post.get("raw_text", "")))
    content_hash = post.get("content_hash") or _content_hash(raw_text)
    post_id = post.get("post_id") or content_hash
    return {
        "post_id": str(post_id),
        "post_url": str(post.get("post_url", "")),
        "raw_text": raw_text,
        "author_name": str(post.get("author_name", profile.get("display_name", ""))),
        "posted_at_text": str(post.get("posted_at_text", "")),
        "fetched_at": str(post.get("fetched_at", _now())),
        "content_hash": str(content_hash),
        "source": str(post.get("source", "playwright")),
    }


def _error_message(post: dict[str, Any]) -> str:
    message = post.get("message") or post.get("error") or "LinkedIn check failed."
    return str(message)


def check_for_new_posts(profile_id: str) -> list[dict[str, Any]]:
    profile = load_tracked_profile(profile_id)
    print(f"Checking LinkedIn creator for new posts: {profile_id}")
    try:
        fetched_posts = fetch_recent_profile_posts(
            profile["profile_url"],
            max_posts=LINKEDIN_CHECK_MAX_POSTS,
        )
    except Exception as exc:
        fetched_posts = [{"error": str(exc), "source": "playwright"}]

    profile["last_checked_at"] = _now()
    errors = [_error_message(post) for post in fetched_posts if isinstance(post, dict) and post.get("error")]
    if errors:
        profile["last_error"] = "; ".join(errors)
        save_tracked_profile(profile)
        print(f"LinkedIn creator check failed: {profile['last_error']}")
        return []

    seen_posts = list(profile.get("seen_posts", []))
    seen_ids = {post.get("post_id") for post in seen_posts}
    seen_hashes = {post.get("content_hash") for post in seen_posts}
    new_posts = []
    for raw_post in fetched_posts:
        if not isinstance(raw_post, dict) or not _clean_text(str(raw_post.get("raw_text", ""))):
            continue
        post = _normalize_post_record(raw_post, profile)
        if post["post_id"] in seen_ids or post["content_hash"] in seen_hashes:
            continue
        seen_posts.append(post)
        seen_ids.add(post["post_id"])
        seen_hashes.add(post["content_hash"])
        new_posts.append(post)

    profile["seen_posts"] = seen_posts
    profile["last_error"] = "" if new_posts or fetched_posts else "No visible LinkedIn posts were found."
    save_tracked_profile(profile)
    print(f"Creator check stored {len(new_posts)} new post(s).")
    return new_posts


def list_unused_posts(profile_id: str) -> list[dict[str, Any]]:
    return _unused_posts_from_profile(load_tracked_profile(profile_id))


def mark_post_used(profile_id: str, post_id: str) -> None:
    profile = load_tracked_profile(profile_id)
    used_post_ids = list(profile.get("used_post_ids", []))
    if post_id and post_id not in used_post_ids:
        used_post_ids.append(post_id)
        profile["used_post_ids"] = used_post_ids
        save_tracked_profile(profile)
        print(f"Marked tracked creator post as used: {post_id}")
