from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.config import USER_PROFILE_PATH, ensure_local_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_profile() -> dict[str, Any]:
    return {
        "writing_style": None,
        "writing_style_source": "",
        "writing_style_examples": [],
        "resume_profile": None,
        "resume_source": "",
        "resume_skipped": False,
        "created_at": "",
        "updated_at": "",
    }


def _read_json(default: Any) -> Any:
    if not USER_PROFILE_PATH.exists():
        return default
    try:
        return json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"User profile file was invalid JSON, using default: {USER_PROFILE_PATH}")
        return default


def _write_json(data: dict[str, Any]) -> None:
    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def load_user_profile() -> dict[str, Any]:
    ensure_local_db()
    profile = _read_json(_default_profile())
    if not isinstance(profile, dict):
        return _default_profile()
    merged = _default_profile()
    merged.update(profile)
    return merged


def save_user_profile(profile: dict[str, Any]) -> dict[str, Any]:
    ensure_local_db()
    existing = load_user_profile()
    timestamp = _now()
    merged = _default_profile()
    merged.update(existing)
    merged.update(profile)
    merged["created_at"] = merged.get("created_at") or timestamp
    merged["updated_at"] = timestamp
    _write_json(merged)
    print("Saved global user profile.")
    return merged


def reset_user_profile() -> None:
    if USER_PROFILE_PATH.exists():
        USER_PROFILE_PATH.unlink()
        print("Deleted global user profile.")


def has_saved_writing_style() -> bool:
    style = load_user_profile().get("writing_style")
    return isinstance(style, dict) and bool(style.get("name") or style.get("summary"))


def has_saved_resume_profile() -> bool:
    resume_profile = load_user_profile().get("resume_profile")
    return isinstance(resume_profile, dict) and bool(
        resume_profile.get("full_name")
        or resume_profile.get("headline")
        or resume_profile.get("skills")
        or resume_profile.get("raw_notes")
    )


def resume_was_skipped() -> bool:
    return bool(load_user_profile().get("resume_skipped"))


def get_generation_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    profile = load_user_profile()
    writing_style = profile.get("writing_style")
    resume_profile = profile.get("resume_profile")
    return (
        writing_style if isinstance(writing_style, dict) else {},
        resume_profile if isinstance(resume_profile, dict) else {},
    )


def update_writing_style(
    style: dict[str, Any],
    source: str,
    examples: list[str] | None = None,
) -> dict[str, Any]:
    return save_user_profile(
        {
            "writing_style": style,
            "writing_style_source": source,
            "writing_style_examples": examples or [],
        }
    )


def update_resume_profile(
    resume_profile: dict[str, Any],
    source: str,
    skipped: bool = False,
) -> dict[str, Any]:
    return save_user_profile(
        {
            "resume_profile": resume_profile,
            "resume_source": source,
            "resume_skipped": skipped,
        }
    )
