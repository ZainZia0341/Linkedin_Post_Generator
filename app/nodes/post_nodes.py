from __future__ import annotations

import json
from typing import Any

from app.config import MAX_REVIEW_ATTEMPTS, TAVILY_SEARCH_RESULTS
from app.graph_state_schema import GraphState
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import GeneratedPost, PostReview
from app.llms.prompts import (
    POST_GENERATION_SYSTEM_PROMPT,
    POST_GENERATION_USER_PROMPT,
    POST_MODIFICATION_SYSTEM_PROMPT,
    POST_MODIFICATION_USER_PROMPT,
    POST_REVIEW_SYSTEM_PROMPT,
    POST_REVIEW_USER_PROMPT,
)
from app.post_formatting import format_linkedin_post, formatting_issues
from app.travily_tool import run_tavily_post_research


def _state_config(state: GraphState) -> LLMConfig:
    return LLMConfig(
        provider=state.get("provider", ""),
        model=state.get("model", ""),
        api_key=state.get("api_key", ""),
    )


def _json(data: Any) -> str:
    if data is None:
        return "{}"
    if hasattr(data, "model_dump"):
        return data.model_dump_json(indent=2)
    return json.dumps(data, indent=2, ensure_ascii=True)


def _latest_user_message(state: GraphState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _research_notes(state: GraphState) -> str:
    results = state.get("search_results", [])
    if not results:
        return "No external search results were available."
    return "\n".join(
        (
            f"- Query: {result.get('query', '')}\n"
            f"  Title: {result.get('title', 'Untitled')}\n"
            f"  Summary: {result.get('content', result.get('summary', ''))}\n"
            f"  URL: {result.get('url', '')}"
        )
        for result in results[: max(TAVILY_SEARCH_RESULTS, len(results))]
    )


def web_research_node(state: GraphState) -> dict[str, object]:
    topic = state.get("topic", "").strip()
    latest_user_message = _latest_user_message(state)
    research_topic = topic or latest_user_message
    if not research_topic:
        print("Web research skipped: no topic or user message provided.")
        return {"search_results": []}
    results = run_tavily_post_research(
        topic=research_topic,
        llm_config=_state_config(state),
        user_message=latest_user_message,
    )
    print(f"Web research returned {len(results)} result item(s).")
    return {
        "search_results": results,
        "search_queries": list(dict.fromkeys(result.get("query", "") for result in results if result.get("query"))),
    }


def _fallback_generated_post(state: GraphState) -> GeneratedPost:
    topic = state.get("topic", "this topic").strip() or "this topic"
    style = state.get("writing_style") or {}
    resume = state.get("resume_profile") or {}
    generation_style = state.get("generation_style", "Create a post about a topic")
    tone = style.get("tone", "clear and practical") if isinstance(style, dict) else "clear and practical"
    name = resume.get("full_name", "") if isinstance(resume, dict) else ""
    opener = f"I have been thinking about {topic}."
    if name:
        opener = f"As {name}, I have been thinking about {topic}."

    if "mistakes" in generation_style.lower():
        post = (
            f"{opener}\n\n"
            "The mistakes I see most often:\n"
            "1. Starting with the tool before defining the problem.\n"
            "2. Sharing vague claims without a concrete example.\n"
            "3. Skipping the review step before people see the work.\n\n"
            f"Fix those three and {topic} becomes much easier to trust.\n\n"
            "Which one shows up most often?"
        )
    elif "do's and don'ts" in generation_style.lower():
        post = (
            f"{opener}\n\n"
            "Don't:\n"
            "- Chase the trend without understanding the use case.\n"
            "- Turn the post into a list of buzzwords.\n\n"
            "Do:\n"
            "- Explain the practical problem.\n"
            "- Give one example a reader can remember.\n\n"
            f"That is how {topic} becomes useful instead of just noisy.\n\n"
            "What would you add?"
        )
    else:
        post = (
            f"{opener}\n\n"
            "The useful part is not just the idea itself. It is how we turn it into a repeatable habit.\n\n"
            "Three things stand out:\n"
            "1. Start with the real problem, not the tool.\n"
            "2. Keep the workflow simple enough to use when work gets busy.\n"
            "3. Review the output before sharing it with people who trust you.\n\n"
            f"That is the difference between experimenting with {topic} and actually getting value from it.\n\n"
            "What would you add?"
        )
    return GeneratedPost(
        post=post,
        facts_used=[
            result.get("title", "")
            for result in state.get("search_results", [])
            if result.get("title")
        ]
        or ["Deterministic fallback generated without external claims."],
        style_notes=[f"Used {tone} tone."],
        provider=state.get("provider", ""),
        model=state.get("model", ""),
    )


def generate_post_node(state: GraphState) -> dict[str, object]:
    attempts = int(state.get("attempts", 0)) + 1
    updated_state = dict(state)
    updated_state["attempts"] = attempts
    print(f"Generating LinkedIn post, attempt {attempts}.")
    generated = invoke_structured(
        config=_state_config(state),
        schema=GeneratedPost,
        system_prompt=POST_GENERATION_SYSTEM_PROMPT,
        user_prompt=POST_GENERATION_USER_PROMPT.format(
            topic=state.get("topic", ""),
            writing_style=_json(state.get("writing_style")),
            resume_profile=_json(state.get("resume_profile")),
            research_notes=_research_notes(state),
            generation_instructions=state.get("generation_instructions", ""),
            review_feedback=state.get("review_feedback", ""),
        ),
        fallback_factory=lambda: _fallback_generated_post(updated_state),
    )
    formatted_post = format_linkedin_post(generated.post)
    messages = list(state.get("messages", []))
    if not messages or messages[-1].get("content") != formatted_post:
        messages.append({"role": "assistant", "content": formatted_post})
    return {
        "current_post": formatted_post,
        "final_post": formatted_post,
        "attempts": attempts,
        "max_attempts": int(state.get("max_attempts", MAX_REVIEW_ATTEMPTS)),
        "provider": state.get("provider", ""),
        "model": state.get("model", ""),
        "messages": messages,
    }


def _fallback_modified_post(state: GraphState) -> GeneratedPost:
    post = state.get("current_post") or state.get("final_post") or ""
    request = _latest_user_message(state).lower()
    revised = post
    if "shorter" in request or "concise" in request:
        paragraphs = [paragraph for paragraph in post.split("\n\n") if paragraph.strip()]
        revised = "\n\n".join(paragraphs[:3])
    elif "longer" in request or "detail" in request:
        revised = post + "\n\nA practical next step is to test this with one real workflow before scaling it."
    elif "hashtag" in request and "#" not in post:
        revised = post + "\n\n#LinkedIn #CareerGrowth #AI"
    elif "hook" in request:
        revised = "A simple shift changed how I see this:\n\n" + post
    elif "cta" in request or "call to action" in request:
        revised = post.rstrip() + "\n\nWhat would you try first?"
    else:
        revised = post.rstrip() + "\n\nUpdated based on your requested direction."

    return GeneratedPost(
        post=revised,
        facts_used=["Modified from the current post only."],
        style_notes=["Applied deterministic edit fallback."],
        provider=state.get("provider", ""),
        model=state.get("model", ""),
    )


def modify_post_node(state: GraphState) -> dict[str, object]:
    attempts = int(state.get("attempts", 0)) + 1
    updated_state = dict(state)
    updated_state["attempts"] = attempts
    print(f"Modifying LinkedIn post, attempt {attempts}.")
    generated = invoke_structured(
        config=_state_config(state),
        schema=GeneratedPost,
        system_prompt=POST_MODIFICATION_SYSTEM_PROMPT,
        user_prompt=POST_MODIFICATION_USER_PROMPT.format(
            current_post=state.get("current_post") or state.get("final_post", ""),
            user_request=_latest_user_message(state),
            conversation_history=_json(state.get("messages", [])),
            writing_style=_json(state.get("writing_style")),
            resume_profile=_json(state.get("resume_profile")),
            review_feedback=state.get("review_feedback", ""),
        ),
        fallback_factory=lambda: _fallback_modified_post(updated_state),
    )
    formatted_post = format_linkedin_post(generated.post)
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": formatted_post})
    return {
        "current_post": formatted_post,
        "final_post": formatted_post,
        "attempts": attempts,
        "max_attempts": int(state.get("max_attempts", MAX_REVIEW_ATTEMPTS)),
        "provider": state.get("provider", ""),
        "model": state.get("model", ""),
        "messages": messages,
    }


def _fallback_review(state: GraphState) -> PostReview:
    post = state.get("current_post") or state.get("final_post", "")
    issues = []
    if len(post.split()) < 30:
        issues.append("Post is too short to be useful.")
    if "TODO" in post or "[insert" in post.lower():
        issues.append("Post contains placeholder text.")
    if "http" in post and not state.get("search_results"):
        issues.append("Post includes a source-like URL without search context.")
    issues.extend(formatting_issues(post))
    if issues:
        return PostReview(
            passed=False,
            feedback="Fix these issues: " + "; ".join(issues),
            issues=issues,
            revised_prompt_hint="Regenerate with concrete, safe, complete wording.",
        )
    return PostReview(
        passed=True,
        feedback="Post passes basic style, format, and factual-safety checks.",
        issues=[],
        revised_prompt_hint="",
    )


def review_post_node(state: GraphState) -> dict[str, object]:
    print("Reviewing generated post.")
    review = invoke_structured(
        config=_state_config(state),
        schema=PostReview,
        system_prompt=POST_REVIEW_SYSTEM_PROMPT,
        user_prompt=POST_REVIEW_USER_PROMPT.format(
            post=state.get("current_post") or state.get("final_post", ""),
            topic=state.get("topic", ""),
            user_request=_latest_user_message(state),
            writing_style=_json(state.get("writing_style")),
            resume_profile=_json(state.get("resume_profile")),
            research_notes=_research_notes(state),
        ),
        fallback_factory=lambda: _fallback_review(state),
    )
    print(f"Review result: {'passed' if review.passed else 'needs revision'}")
    return {
        "review_passed": review.passed,
        "review_feedback": review.feedback,
        "review": review.model_dump(),
    }
