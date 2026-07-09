from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import SESSION_DIR, SESSION_INDEX_PATH, ensure_local_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Local DB file was invalid JSON, using default: {path}")
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _session_path(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def load_session_index() -> list[dict[str, Any]]:
    ensure_local_db()
    index = _read_json(SESSION_INDEX_PATH, [])
    return index if isinstance(index, list) else []


def save_session_index(index: list[dict[str, Any]]) -> None:
    ensure_local_db()
    _write_json(SESSION_INDEX_PATH, index)


def list_sessions() -> list[dict[str, Any]]:
    return sorted(load_session_index(), key=lambda row: row.get("updated_at", ""), reverse=True)


def create_session(provider: str, model: str) -> dict[str, Any]:
    ensure_local_db()
    index = load_session_index()
    chat_number = len(index) + 1
    session_id = str(uuid4())
    timestamp = _now()
    record: dict[str, Any] = {
        "session_id": session_id,
        "chat_name": f"chat{chat_number}",
        "created_at": timestamp,
        "updated_at": timestamp,
        "provider": provider,
        "model": model,
        "step": "writing_style",
        "writing_style": None,
        "resume_profile": None,
        "current_post": "",
        "messages": [],
        "research_results": None,
    }
    _write_json(_session_path(session_id), record)
    index.append(
        {
            "session_id": session_id,
            "chat_name": record["chat_name"],
            "provider": provider,
            "model": model,
            "created_at": timestamp,
            "updated_at": timestamp,
            "step": record["step"],
        }
    )
    save_session_index(index)
    print(f"Created local chat session: {record['chat_name']} ({session_id})")
    return record


def load_session(session_id: str) -> dict[str, Any] | None:
    ensure_local_db()
    path = _session_path(session_id)
    if not path.exists():
        return None
    record = _read_json(path, None)
    return record if isinstance(record, dict) else None


def save_session(record: dict[str, Any]) -> dict[str, Any]:
    ensure_local_db()
    record = dict(record)
    record.pop("api_key", None)
    record["updated_at"] = _now()
    _write_json(_session_path(record["session_id"]), record)

    index = load_session_index()
    found = False
    for row in index:
        if row.get("session_id") == record["session_id"]:
            row.update(
                {
                    "chat_name": record.get("chat_name", row.get("chat_name")),
                    "provider": record.get("provider", row.get("provider")),
                    "model": record.get("model", row.get("model")),
                    "updated_at": record["updated_at"],
                    "step": record.get("step", row.get("step")),
                }
            )
            found = True
            break
    if not found:
        index.append(
            {
                "session_id": record["session_id"],
                "chat_name": record.get("chat_name", "chat"),
                "provider": record.get("provider", ""),
                "model": record.get("model", ""),
                "created_at": record.get("created_at", record["updated_at"]),
                "updated_at": record["updated_at"],
                "step": record.get("step", ""),
            }
        )
    save_session_index(index)
    print(f"Saved local chat session: {record.get('chat_name', record['session_id'])}")
    return record


def update_session(session_id: str, **changes: Any) -> dict[str, Any]:
    record = load_session(session_id)
    if record is None:
        raise ValueError(f"Session not found: {session_id}")
    record.update(changes)
    return save_session(record)


def append_chat_message(session_id: str, role: str, content: str) -> dict[str, Any]:
    record = load_session(session_id)
    if record is None:
        raise ValueError(f"Session not found: {session_id}")
    messages = list(record.get("messages", []))
    messages.append({"role": role, "content": content, "created_at": _now()})
    record["messages"] = messages
    return save_session(record)

