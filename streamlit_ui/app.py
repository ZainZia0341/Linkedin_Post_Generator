from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DEFAULT_PROVIDER, MAX_REVIEW_ATTEMPTS, PROVIDER_MODELS, get_env_api_key
from app.extract_resume_details import extract_resume_profile, extract_text_from_pdf_bytes
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.llms.llm import LLMConfig, test_provider_api_key
from app.storage import create_session, list_sessions, load_session, save_session
from app.writing_style_extract import (
    builtin_writing_styles,
    extract_writing_style,
    get_builtin_writing_style,
)


def _init_state() -> None:
    st.session_state.setdefault("active_session_id", "")
    st.session_state.setdefault("provider", DEFAULT_PROVIDER)
    st.session_state.setdefault("model", PROVIDER_MODELS[DEFAULT_PROVIDER][0])
    st.session_state.setdefault("api_key", "")
    st.session_state.setdefault("api_key_ok", False)
    st.session_state.setdefault("api_key_signature", "")
    st.session_state.setdefault("style_json", "")
    st.session_state.setdefault("resume_json", "")
    st.session_state.setdefault("research_extra_details", "")


def _config() -> LLMConfig:
    return LLMConfig(
        provider=st.session_state.provider,
        model=st.session_state.model,
        api_key=st.session_state.api_key,
    )


def _json_text(data: Any) -> str:
    return json.dumps(data or {}, indent=2, ensure_ascii=True)


def _parse_json_area(label: str, value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        st.error(f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(parsed, dict):
        st.error(f"{label} must be a JSON object.")
        return None
    return parsed


def _sidebar() -> None:
    st.sidebar.title("Setup")
    providers = list(PROVIDER_MODELS.keys())
    provider_index = providers.index(st.session_state.provider) if st.session_state.provider in providers else 0
    provider = st.sidebar.selectbox("LLM provider", providers, index=provider_index)
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.session_state.model = PROVIDER_MODELS[provider][0]
        st.session_state.api_key_ok = False

    models = PROVIDER_MODELS[st.session_state.provider]
    model_index = models.index(st.session_state.model) if st.session_state.model in models else 0
    model = st.sidebar.selectbox("Model", models, index=model_index)
    if model != st.session_state.model:
        st.session_state.model = model
        st.session_state.api_key_ok = False

    env_key = get_env_api_key(st.session_state.provider)
    default_key = st.session_state.api_key or env_key
    api_key = st.sidebar.text_input("API key", value=default_key, type="password")
    signature = f"{st.session_state.provider}|{st.session_state.model}|{api_key}"
    if signature != st.session_state.api_key_signature:
        st.session_state.api_key_ok = False
        st.session_state.api_key_signature = signature
    st.session_state.api_key = api_key

    if st.sidebar.button("Test API key", use_container_width=True):
        result = test_provider_api_key(_config())
        st.session_state.api_key_ok = result.ok
        if result.ok:
            st.sidebar.success(result.message)
        else:
            st.sidebar.error(result.message)

    if st.sidebar.button("Start new chat", use_container_width=True):
        if not st.session_state.api_key:
            st.sidebar.error("Enter an API key first.")
        elif not st.session_state.api_key_ok:
            st.sidebar.error("Test the API key successfully before starting a new chat.")
        else:
            record = create_session(st.session_state.provider, st.session_state.model)
            st.session_state.active_session_id = record["session_id"]
            st.session_state.style_json = ""
            st.session_state.resume_json = ""
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Chats")
    sessions = list_sessions()
    if not sessions:
        st.sidebar.caption("No chats yet.")
    for row in sessions:
        label = f"{row.get('chat_name', 'chat')} - {row.get('step', '')}"
        if st.sidebar.button(label, key=f"chat-{row['session_id']}", use_container_width=True):
            st.session_state.active_session_id = row["session_id"]
            st.session_state.style_json = ""
            st.session_state.resume_json = ""
            st.rerun()


def _render_style_step(record: dict[str, Any]) -> None:
    st.subheader("Writing Style")
    source = st.radio("Style source", ["Paste previous post", "Use built-in style"], horizontal=True)
    if source == "Paste previous post":
        previous_post = st.text_area("Previous LinkedIn post", height=220)
        if st.button("Extract writing style", use_container_width=True):
            style = extract_writing_style(previous_post, _config())
            st.session_state.style_json = style.model_dump_json(indent=2)
            print("Writing style extracted for UI review.")
    else:
        styles = builtin_writing_styles()
        style_names = [style.name for style in styles]
        selected = st.selectbox("Built-in style", style_names)
        style = get_builtin_writing_style(selected)
        st.session_state.style_json = style.model_dump_json(indent=2)

    style_json = st.text_area(
        "Review or edit writing style JSON",
        value=st.session_state.style_json or _json_text(record.get("writing_style")),
        height=280,
    )
    if st.button("Save style and continue", use_container_width=True):
        parsed = _parse_json_area("Writing style", style_json)
        if parsed is not None:
            record["writing_style"] = parsed
            record["step"] = "resume"
            save_session(record)
            st.session_state.style_json = ""
            st.rerun()


def _render_resume_step(record: dict[str, Any]) -> None:
    st.subheader("Resume Profile")
    uploaded = st.file_uploader("Upload resume PDF (optional)", type=["pdf"])
    pasted_text = st.text_area("Or paste resume text", height=180)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Extract resume details", use_container_width=True):
            resume_text = pasted_text
            if uploaded is not None:
                resume_text = extract_text_from_pdf_bytes(uploaded.getvalue())
            profile = extract_resume_profile(resume_text, _config())
            st.session_state.resume_json = profile.model_dump_json(indent=2)
            print("Resume profile extracted for UI review.")
    with col2:
        if st.button("Skip resume", use_container_width=True):
            record["resume_profile"] = {}
            record["step"] = "choose_mode"
            save_session(record)
            st.rerun()

    resume_json = st.text_area(
        "Review or edit resume JSON",
        value=st.session_state.resume_json or _json_text(record.get("resume_profile")),
        height=280,
    )
    if st.button("Save resume and continue", use_container_width=True):
        parsed = _parse_json_area("Resume profile", resume_json)
        if parsed is not None:
            record["resume_profile"] = parsed
            record["step"] = "choose_mode"
            save_session(record)
            st.session_state.resume_json = ""
            st.rerun()


def _render_mode_step(record: dict[str, Any]) -> None:
    st.subheader("Choose Workflow")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Give a topic")
        st.write("Generate a LinkedIn post from your topic, style, resume profile, and web research.")
        if st.button("Generate from topic", use_container_width=True):
            record["step"] = "topic"
            save_session(record)
            st.rerun()
    with col2:
        st.markdown("### Research trending topics")
        st.write("Find timely post angles based on your resume/profile. Results are read-only.")
        if st.button("Research trends", use_container_width=True):
            record["step"] = "research"
            save_session(record)
            st.rerun()


def _render_topic_step(record: dict[str, Any]) -> None:
    st.subheader("Generate Post")
    topic = st.text_input("Topic")
    if st.button("Run AI workflow", use_container_width=True):
        if not topic.strip():
            st.error("Enter a topic first.")
            return
        with st.spinner("Generating and reviewing the post..."):
            graph_result = run_post_generation(
                {
                    "workflow_mode": "generate",
                    "topic": topic,
                    "writing_style": record.get("writing_style") or {},
                    "resume_profile": record.get("resume_profile") or {},
                    "messages": [{"role": "user", "content": topic}],
                    "provider": st.session_state.provider,
                    "model": st.session_state.model,
                    "api_key": st.session_state.api_key,
                    "attempts": 0,
                    "max_attempts": MAX_REVIEW_ATTEMPTS,
                }
            )
        record.update(
            {
                "topic": topic,
                "current_post": graph_result.get("final_post", ""),
                "messages": graph_result.get("messages", []),
                "search_results": graph_result.get("search_results", []),
                "search_queries": graph_result.get("search_queries", []),
                "review": graph_result.get("review", {}),
                "provider": st.session_state.provider,
                "model": st.session_state.model,
                "step": "chat",
            }
        )
        save_session(record)
        st.rerun()


def _render_chat_step(record: dict[str, Any]) -> None:
    st.subheader("Post Editor")
    st.text_area("Current LinkedIn post", value=record.get("current_post", ""), height=320)
    st.caption(f"Provider: {record.get('provider', '')} | Model: {record.get('model', '')}")
    if record.get("search_queries"):
        with st.expander("Web searches used"):
            for query in record.get("search_queries", []):
                st.write(f"- {query}")

    for message in record.get("messages", []):
        role = "assistant" if message.get("role") == "assistant" else "user"
        with st.chat_message(role):
            st.write(message.get("content", ""))

    user_message = st.chat_input("Ask for a change to this post")
    if user_message:
        messages = list(record.get("messages", []))
        messages.append({"role": "user", "content": user_message})
        with st.spinner("Applying the requested edit..."):
            graph_result = run_post_chat_edit(
                {
                    "workflow_mode": "chat",
                    "topic": record.get("topic", ""),
                    "writing_style": record.get("writing_style") or {},
                    "resume_profile": record.get("resume_profile") or {},
                    "current_post": record.get("current_post", ""),
                    "messages": messages,
                    "provider": st.session_state.provider,
                    "model": st.session_state.model,
                    "api_key": st.session_state.api_key,
                    "attempts": 0,
                    "max_attempts": MAX_REVIEW_ATTEMPTS,
                }
            )
        record["current_post"] = graph_result.get("final_post", record.get("current_post", ""))
        record["messages"] = graph_result.get("messages", messages)
        record["search_results"] = graph_result.get("search_results", record.get("search_results", []))
        record["search_queries"] = graph_result.get("search_queries", record.get("search_queries", []))
        record["review"] = graph_result.get("review", {})
        record["provider"] = st.session_state.provider
        record["model"] = st.session_state.model
        save_session(record)
        st.rerun()


def _render_research_step(record: dict[str, Any]) -> None:
    st.subheader("Trending Topic Research")
    if not record.get("resume_profile"):
        st.info("No resume profile is saved for this chat. Add a short profile so the research has direction.")
        st.session_state.research_extra_details = st.text_area(
            "Profile details for research",
            value=st.session_state.research_extra_details,
            height=160,
        )
    if st.button("Run deep research", use_container_width=True):
        with st.spinner("Researching topic ideas..."):
            results = research_trending_topics(
                resume_profile=record.get("resume_profile"),
                llm_config=_config(),
                extra_details=st.session_state.research_extra_details,
            )
        record["research_results"] = results.model_dump()
        save_session(record)
        print("Deep research results saved.")
        st.rerun()

    results = record.get("research_results")
    if results:
        if results.get("needs_more_user_details"):
            st.warning("Add profile details before running research.")
        for finding in results.get("findings", []):
            st.markdown(f"### {finding.get('title', 'Untitled')}")
            st.write(finding.get("summary", ""))
            st.write(f"Why it matters: {finding.get('why_it_matters', '')}")
            st.write(f"Post angle: {finding.get('suggested_post_angle', '')}")
            if finding.get("source_url"):
                st.caption(finding["source_url"])


def main() -> None:
    st.set_page_config(page_title="LinkedIn Post Generator", layout="wide")
    _init_state()
    _sidebar()

    st.title("LinkedIn Post Generator")
    if not st.session_state.active_session_id:
        st.info("Set up your provider in the sidebar, test the API key, then start a new chat.")
        return

    record = load_session(st.session_state.active_session_id)
    if record is None:
        st.error("Selected chat was not found in local storage.")
        return

    step = record.get("step", "writing_style")
    if step == "writing_style":
        _render_style_step(record)
    elif step == "resume":
        _render_resume_step(record)
    elif step == "choose_mode":
        _render_mode_step(record)
    elif step == "topic":
        _render_topic_step(record)
    elif step == "research":
        _render_research_step(record)
    elif step == "chat":
        _render_chat_step(record)
    else:
        st.error(f"Unknown chat step: {step}")


if __name__ == "__main__":
    main()
