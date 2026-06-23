from __future__ import annotations

from app.graph_state_schema import GraphState
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import GuardrailDecision
from app.llms.prompts import GUARDRAIL_SYSTEM_PROMPT, GUARDRAIL_USER_PROMPT

BLOCKED_REPLY = "Sorry, I can not help you with that. I can only modify this generated LinkedIn post."


def _latest_user_message(state: GraphState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _fallback_guardrail(state: GraphState) -> GuardrailDecision:
    user_message = _latest_user_message(state).lower()
    has_post = bool(state.get("current_post") or state.get("final_post"))
    if not has_post:
        return GuardrailDecision(route="blocked", reason="No generated post exists yet.")

    edit_terms = [
        "edit",
        "change",
        "rewrite",
        "make",
        "shorter",
        "longer",
        "tone",
        "hook",
        "cta",
        "hashtag",
        "remove",
        "add",
        "polish",
        "improve",
        "replace",
        "format",
        "post",
    ]
    if any(term in user_message for term in edit_terms):
        return GuardrailDecision(route="modify_post", reason="Message asks to modify the post.")
    return GuardrailDecision(route="blocked", reason="Message is not about modifying the current post.")


def guardrail_node(state: GraphState) -> dict[str, object]:
    config = LLMConfig(
        provider=state.get("provider", ""),
        model=state.get("model", ""),
        api_key=state.get("api_key", ""),
    )
    user_message = _latest_user_message(state)
    decision = invoke_structured(
        config=config,
        schema=GuardrailDecision,
        system_prompt=GUARDRAIL_SYSTEM_PROMPT,
        user_prompt=GUARDRAIL_USER_PROMPT.format(
            has_post=bool(state.get("current_post") or state.get("final_post")),
            user_message=user_message,
        ),
        fallback_factory=lambda: _fallback_guardrail(state),
    )
    print(f"Guardrail route: {decision.route} ({decision.reason})")
    return {"route": decision.route, "guardrail_reason": decision.reason}


def hardcoded_guardrail_node(state: GraphState) -> dict[str, object]:
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": BLOCKED_REPLY})
    print("Guardrail blocked off-topic request.")
    return {
        "guardrail_reply": BLOCKED_REPLY,
        "messages": messages,
        "final_post": state.get("current_post", state.get("final_post", "")),
    }
