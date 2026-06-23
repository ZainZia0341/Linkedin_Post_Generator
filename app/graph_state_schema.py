from __future__ import annotations

from typing import Any, Literal, TypedDict


class GraphState(TypedDict, total=False):
    workflow_mode: Literal["generate", "chat"]
    topic: str
    writing_style: dict[str, Any]
    resume_profile: dict[str, Any]
    current_post: str
    final_post: str
    messages: list[dict[str, Any]]
    search_results: list[dict[str, Any]]
    search_queries: list[str]
    provider: str
    model: str
    api_key: str
    route: Literal["modify_post", "blocked"]
    guardrail_reason: str
    guardrail_reply: str
    review_passed: bool
    review_feedback: str
    review: dict[str, Any]
    attempts: int
    max_attempts: int
    error: str
