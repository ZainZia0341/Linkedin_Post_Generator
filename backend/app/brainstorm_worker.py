from __future__ import annotations

from app.brainstorm_jobs import run_brainstorm_worker


def handler(event, _context):
    run_brainstorm_worker(event)
    return {"ok": True}
