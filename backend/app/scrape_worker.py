from __future__ import annotations

from typing import Any

from app.api.services import run_scrape_worker


def handler(event: dict[str, Any], context: Any) -> dict[str, bool]:
    run_scrape_worker(event)
    return {"ok": True}
