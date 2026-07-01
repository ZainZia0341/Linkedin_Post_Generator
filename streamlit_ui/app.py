from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (
    DEFAULT_PROVIDER,
    LINKEDIN_AUTOMATION_MODE,
    LINKEDIN_DEFAULT_TRACK_URL,
    MAX_REVIEW_ATTEMPTS,
    PROVIDER_MODELS,
    get_env_api_key,
)
from app.creator_tracking import (
    add_tracked_profile,
    check_for_new_posts,
    list_tracked_profiles,
    list_unused_posts,
    load_tracked_profile,
    mark_post_used,
    seed_default_profile_if_empty,
)
from app.extract_resume_details import extract_resume_profile, extract_text_from_pdf_bytes
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.linkedin_playwright_scraper import BOOTSTRAP_REQUIRED_MESSAGE, has_bootstrapped_burner_session
from app.llms.llm import LLMConfig, test_provider_api_key
from app.storage import create_session, list_sessions, load_session, save_session
from app.user_profile import (
    get_generation_profile,
    has_saved_resume_profile,
    has_saved_writing_style,
    load_user_profile,
    reset_user_profile,
    resume_was_skipped,
    update_resume_profile,
    update_writing_style,
)
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
    st.session_state.setdefault("tracked_profile_url", "")
    st.session_state.setdefault("tracked_profile_id", "")


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


def _resume_status() -> str:
    if has_saved_resume_profile():
        return "Saved"
    if resume_was_skipped():
        return "Skipped"
    return "Not saved"


def _apply_saved_profile_to_new_session(record: dict[str, Any]) -> dict[str, Any]:
    profile = load_user_profile()
    writing_style = profile.get("writing_style")
    resume_profile = profile.get("resume_profile")

    if isinstance(writing_style, dict) and writing_style:
        record["writing_style"] = writing_style
        record["writing_style_snapshot"] = writing_style
        if isinstance(resume_profile, dict):
            record["resume_profile"] = resume_profile
            record["resume_profile_snapshot"] = resume_profile
        if profile.get("resume_skipped"):
            record["resume_profile"] = {}
            record["resume_skipped_snapshot"] = True
        record["step"] = "choose_mode" if isinstance(resume_profile, dict) or profile.get("resume_skipped") else "resume"
    else:
        record["step"] = "writing_style"

    return save_session(record)


def _generation_context(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    saved_style, saved_resume = get_generation_profile()
    writing_style = saved_style or record.get("writing_style") or {}
    resume_profile = saved_resume or record.get("resume_profile") or {}
    return writing_style, resume_profile


def _creator_topic_seed(post: dict[str, Any]) -> str:
    return (
        "Creator source post:\n"
        f"{post.get('raw_text', '')}\n\n"
        "Task:\n"
        "Write a new LinkedIn post inspired by the topic of this creator post. "
        "Do not copy phrasing. Use my saved writing style and profile."
    )


def _post_preview(text: str, limit: int = 420) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _selected_tracked_profile_id() -> str:
    profiles = list_tracked_profiles()
    profile_ids = [profile["profile_id"] for profile in profiles]
    if st.session_state.tracked_profile_id in profile_ids:
        return st.session_state.tracked_profile_id
    return profile_ids[0] if profile_ids else ""


def _render_creator_post_details(post: dict[str, Any], index: int, compact: bool = False) -> None:
    st.markdown(f"**Post {index + 1}**")
    meta_parts = [
        part
        for part in (
            post.get("posted_at_text"),
            f"Fetched: {post.get('fetched_at')}" if post.get("fetched_at") else "",
        )
        if part
    ]
    if meta_parts:
        st.caption(" | ".join(meta_parts))
    st.write(_post_preview(post.get("raw_text", ""), 260 if compact else 900))
    if post.get("post_url"):
        st.caption(post["post_url"])
    if not compact and post.get("post_id"):
        st.caption(f"Post ID: {post['post_id']}")


def _run_generation(
    record: dict[str, Any],
    topic: str,
    source_metadata: dict[str, Any] | None = None,
) -> bool:
    writing_style, resume_profile = _generation_context(record)
    if not writing_style:
        st.error("Save a writing style before generating.")
        return False

    graph_result = run_post_generation(
        {
            "workflow_mode": "generate",
            "topic": topic,
            "writing_style": writing_style,
            "resume_profile": resume_profile,
            "messages": [{"role": "user", "content": topic}],
            "provider": st.session_state.provider,
            "model": st.session_state.model,
            "api_key": st.session_state.api_key,
            "attempts": 0,
            "max_attempts": MAX_REVIEW_ATTEMPTS,
        }
    )

    final_post = graph_result.get("final_post", "")
    if not final_post:
        st.error("The workflow did not return a post.")
        return False

    metadata = source_metadata or {"topic_source": "manual"}
    record.update(
        {
            "topic": topic,
            "topic_source": metadata.get("topic_source", "manual"),
            "writing_style_snapshot": writing_style,
            "resume_profile_snapshot": resume_profile,
            "current_post": final_post,
            "messages": graph_result.get("messages", []),
            "search_results": graph_result.get("search_results", []),
            "search_queries": graph_result.get("search_queries", []),
            "review": graph_result.get("review", {}),
            "provider": st.session_state.provider,
            "model": st.session_state.model,
            "step": "chat",
        }
    )
    record.update(metadata)
    save_session(record)

    if metadata.get("topic_source") == "tracked_creator":
        mark_post_used(str(metadata.get("source_profile_id", "")), str(metadata.get("source_post_id", "")))
    return True


def _open_session_step(step: str) -> None:
    if not st.session_state.active_session_id:
        st.sidebar.info("Start or select a chat first.")
        return
    record = load_session(st.session_state.active_session_id)
    if record is None:
        st.sidebar.error("Selected chat was not found.")
        return
    profile = load_user_profile()
    if step == "writing_style" and isinstance(profile.get("writing_style"), dict):
        record["writing_style"] = profile["writing_style"]
        st.session_state.style_json = _json_text(profile["writing_style"])
    if step == "resume" and isinstance(profile.get("resume_profile"), dict):
        record["resume_profile"] = profile["resume_profile"]
        st.session_state.resume_json = _json_text(profile["resume_profile"])
    record["step"] = step
    save_session(record)
    st.rerun()


def _render_saved_profile_sidebar() -> None:
    with st.sidebar.expander("Saved Profile"):
        st.write(f"Writing style: {'Saved' if has_saved_writing_style() else 'Not saved'}")
        st.write(f"Resume/profile: {_resume_status()}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Edit style", use_container_width=True):
                _open_session_step("writing_style")
        with col2:
            if st.button("Edit resume", use_container_width=True):
                _open_session_step("resume")
        if st.button("Reset saved profile", use_container_width=True):
            reset_user_profile()
            st.session_state.style_json = ""
            st.session_state.resume_json = ""
            st.rerun()


def _render_tracked_creators_sidebar() -> None:
    seed_default_profile_if_empty()
    profiles = list_tracked_profiles()
    with st.sidebar.expander("Tracked Creators"):
        st.caption(f"Mode: {LINKEDIN_AUTOMATION_MODE}")
        st.warning("Read-only automation. Use logged-out mode or a manually bootstrapped burner session only.")
        bootstrap_required = LINKEDIN_AUTOMATION_MODE.strip().lower() == "burner" and not has_bootstrapped_burner_session()
        if bootstrap_required:
            st.info(BOOTSTRAP_REQUIRED_MESSAGE)
        st.session_state.tracked_profile_url = st.text_input(
            "LinkedIn profile URL",
            value=st.session_state.tracked_profile_url,
            placeholder=LINKEDIN_DEFAULT_TRACK_URL,
        )
        if st.button("Add creator", use_container_width=True):
            try:
                profile = add_tracked_profile(st.session_state.tracked_profile_url or None)
                st.session_state.tracked_profile_id = profile["profile_id"]
                st.success(f"Added {profile['display_name']}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        profiles = list_tracked_profiles()
        if not profiles:
            st.caption("No tracked creators yet.")
            return

        profile_ids = [profile["profile_id"] for profile in profiles]
        if st.session_state.tracked_profile_id not in profile_ids:
            st.session_state.tracked_profile_id = profile_ids[0]
        selected_index = profile_ids.index(st.session_state.tracked_profile_id)
        labels = [
            f"{profile.get('display_name', profile['profile_id'])} ({profile.get('unused_count', 0)} unused)"
            for profile in profiles
        ]
        selected_label = st.selectbox("Tracked creator", labels, index=selected_index)
        selected_profile_id = profiles[labels.index(selected_label)]["profile_id"]
        st.session_state.tracked_profile_id = selected_profile_id
        selected_profile = load_tracked_profile(selected_profile_id)

        st.write(f"Seen posts: {selected_profile.get('seen_count', 0)}")
        st.write(f"Used posts: {selected_profile.get('used_count', 0)}")
        st.write(f"Unused posts: {selected_profile.get('unused_count', 0)}")
        st.caption(f"Last checked: {selected_profile.get('last_checked_at') or 'Never'}")
        if selected_profile.get("last_error"):
            st.warning(selected_profile["last_error"])

        unused_posts = list_unused_posts(selected_profile_id)
        if unused_posts:
            with st.expander("Unused post previews"):
                for index, post in enumerate(unused_posts[:5]):
                    _render_creator_post_details(post, index, compact=True)
                    if index < min(len(unused_posts), 5) - 1:
                        st.divider()

        if st.button("Check for new posts", use_container_width=True, disabled=bootstrap_required):
            with st.spinner("Checking LinkedIn recent activity..."):
                new_posts = check_for_new_posts(selected_profile_id)
            selected_profile = load_tracked_profile(selected_profile_id)
            if selected_profile.get("last_error"):
                st.warning(selected_profile["last_error"])
            elif new_posts:
                st.success(f"Stored {len(new_posts)} new post(s).")
            else:
                st.info("No new posts found.")
            st.rerun()


def _render_tracked_posts_overview() -> None:
    profile_id = _selected_tracked_profile_id()
    if not profile_id:
        return

    profile = load_tracked_profile(profile_id)
    unused_posts = list_unused_posts(profile_id)
    if not unused_posts:
        return

    st.subheader(f"Tracked Creator Posts: {profile.get('display_name', profile_id)}")
    st.caption(
        f"Seen: {profile.get('seen_count', 0)} | "
        f"Used: {profile.get('used_count', 0)} | "
        f"Unused: {profile.get('unused_count', 0)} | "
        f"Last checked: {profile.get('last_checked_at') or 'Never'}"
    )
    for index, post in enumerate(unused_posts):
        with st.expander(f"Post {index + 1}", expanded=index == 0):
            _render_creator_post_details(post, index)


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
            record = _apply_saved_profile_to_new_session(record)
            st.session_state.active_session_id = record["session_id"]
            st.session_state.style_json = ""
            st.session_state.resume_json = ""
            st.rerun()

    st.sidebar.divider()
    _render_saved_profile_sidebar()
    _render_tracked_creators_sidebar()
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
    previous_post = ""
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
            record["step"] = "choose_mode" if has_saved_resume_profile() or resume_was_skipped() else "resume"
            update_writing_style(
                parsed,
                "previous_post" if source == "Paste previous post" else "builtin",
                [previous_post] if previous_post.strip() else None,
            )
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
            update_resume_profile({}, "skipped", skipped=True)
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
            update_resume_profile(parsed, "pdf" if uploaded is not None else "text", skipped=False)
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


def _render_tracked_topic_source(record: dict[str, Any]) -> None:
    seed_default_profile_if_empty()
    profiles = list_tracked_profiles()
    if not profiles:
        st.info("Add a tracked creator in the sidebar first.")
        return

    labels = [
        f"{profile.get('display_name', profile['profile_id'])} ({profile.get('unused_count', 0)} unused)"
        for profile in profiles
    ]
    selected_label = st.selectbox("Tracked creator", labels)
    selected_profile = profiles[labels.index(selected_label)]
    unused_posts = list_unused_posts(selected_profile["profile_id"])
    if not unused_posts:
        st.info("No unused posts are available. Check for new posts in the sidebar.")
        return

    for index, post in enumerate(unused_posts):
        preview = post.get("raw_text", "")
        if len(preview) > 650:
            preview = preview[:650].rstrip() + "..."
        st.markdown(f"#### Source post {index + 1}")
        st.write(preview)
        if post.get("post_url"):
            st.caption(post["post_url"])
        st.caption(f"Fetched: {post.get('fetched_at', '')}")
        if st.button("Use this post as topic", key=f"use-source-post-{selected_profile['profile_id']}-{index}", use_container_width=True):
            topic_seed = _creator_topic_seed(post)
            source_metadata = {
                "topic_source": "tracked_creator",
                "source_profile_id": selected_profile["profile_id"],
                "source_post_id": post.get("post_id") or post.get("content_hash", ""),
                "source_post_url": post.get("post_url", ""),
                "source_post_text": post.get("raw_text", ""),
            }
            with st.spinner("Generating and reviewing the post..."):
                if _run_generation(record, topic_seed, source_metadata):
                    st.rerun()


def _render_topic_step(record: dict[str, Any]) -> None:
    st.subheader("Generate Post")
    topic_source = st.radio("Topic source", ["Manual topic", "Tracked creator post"], horizontal=True)
    if topic_source == "Tracked creator post":
        _render_tracked_topic_source(record)
        return

    topic = st.text_input("Topic")
    if st.button("Run AI workflow", use_container_width=True):
        if not topic.strip():
            st.error("Enter a topic first.")
            return
        with st.spinner("Generating and reviewing the post..."):
            if _run_generation(record, topic):
                st.rerun()


def _render_chat_step(record: dict[str, Any]) -> None:
    st.subheader("Post Editor")
    st.text_area("Current LinkedIn post", value=record.get("current_post", ""), height=320)
    st.caption(f"Provider: {record.get('provider', '')} | Model: {record.get('model', '')}")
    if record.get("topic_source") == "tracked_creator":
        with st.expander("Source creator post"):
            if record.get("source_post_url"):
                st.caption(record["source_post_url"])
            st.write(record.get("source_post_text", ""))
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
        writing_style, resume_profile = _generation_context(record)
        with st.spinner("Applying the requested edit..."):
            graph_result = run_post_chat_edit(
                {
                    "workflow_mode": "chat",
                    "topic": record.get("topic", ""),
                    "writing_style": record.get("writing_style_snapshot") or writing_style,
                    "resume_profile": record.get("resume_profile_snapshot") or resume_profile,
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
    st.subheader("Recent Tech Trend Discovery")
    st.caption(
        "Find recent launches, releases, announcements, and newly trending technology topics "
        "based on the stack keywords in your resume/profile."
    )
    _, saved_resume_profile = get_generation_profile()
    resume_profile = saved_resume_profile or record.get("resume_profile")
    if not resume_profile:
        st.info("No resume profile is saved for this chat. Add a short profile so the research has direction.")
        st.session_state.research_extra_details = st.text_area(
            "Profile details for research",
            value=st.session_state.research_extra_details,
            height=160,
        )
    if st.button("Run recent trend research", use_container_width=True):
        with st.spinner("Searching recent technology news and launches..."):
            results = research_trending_topics(
                resume_profile=resume_profile,
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
        if results.get("status_message"):
            engine = results.get("research_engine") or "research"
            st.info(f"{engine}: {results['status_message']}")
        for finding in results.get("findings", []):
            st.markdown(f"### {finding.get('title', 'Untitled')}")
            st.write(finding.get("summary", ""))
            if finding.get("recency_signal"):
                st.write(f"Recent signal: {finding.get('recency_signal', '')}")
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
        _render_tracked_posts_overview()
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
