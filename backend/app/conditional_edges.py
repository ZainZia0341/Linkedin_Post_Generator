from __future__ import annotations

from app.graph_state_schema import GraphState


def route_after_memory(state: GraphState) -> str:
    mode = state.get("workflow_mode", "generate")
    if mode == "chat":
        return "guardrail"
    return "web_research"


def route_guardrail_decision(state: GraphState) -> str:
    if state.get("route") == "modify_post":
        return "web_research"
    return "hardcoded_guardrail"


def route_after_research(state: GraphState) -> str:
    if state.get("workflow_mode") == "chat":
        return "modify_post"
    return "generate_post"


def route_after_review(state: GraphState) -> str:
    if state.get("review_passed"):
        return "done"

    attempts = int(state.get("attempts", 0))
    max_attempts = int(state.get("max_attempts", 3))
    if attempts >= max_attempts:
        print("Review failed but max attempts reached; returning latest post.")
        return "done"

    if state.get("workflow_mode") == "chat":
        return "retry_modify"
    return "retry_generate"
