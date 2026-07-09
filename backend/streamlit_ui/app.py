from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st


DEFAULT_API_BASE_URL = (
    os.getenv("LINKEDIN_API_BASE_URL")
    or os.getenv("API_BASE_URL")
    or "http://localhost:7860"
)
REQUEST_TIMEOUT = 180.0
LONG_REQUEST_TIMEOUT = 900.0


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def init_state() -> None:
    defaults: dict[str, Any] = {
        "api_base_url": DEFAULT_API_BASE_URL,
        "selected_user_id": "",
        "last_thread": None,
        "last_comment": None,
        "last_brainstorm": None,
        "last_scrape": None,
        "last_recent_scrape": None,
        "last_recent_db_activities": None,
        "last_bulk_import": None,
        "last_profile_scrape": None,
        "last_creator_profile_details": None,
        "last_specific_creator_profile": None,
        "last_activity_thread": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --surface: #ffffff;
            --muted-surface: #f6f8fb;
            --ink: #17202a;
            --muted-ink: #5f6b7a;
            --line: #d8dee8;
            --accent: #2457d6;
            --success: #0e7c59;
            --warning: #a05a00;
        }

        [data-testid="stAppViewContainer"] {
            background:
                linear-gradient(180deg, #f6f8fb 0%, #eef3f7 44%, #f8fafc 100%);
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] h4,
        [data-testid="stAppViewContainer"] h5,
        [data-testid="stAppViewContainer"] h6,
        [data-testid="stAppViewContainer"] p,
        [data-testid="stAppViewContainer"] label,
        [data-testid="stAppViewContainer"] span,
        [data-testid="stAppViewContainer"] small,
        [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"],
        [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] {
            color: var(--ink) !important;
        }

        .block-container {
            max-width: 1320px;
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        h1 {
            font-size: 2rem;
            margin-bottom: 0.15rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.25rem;
            border-bottom: 1px solid var(--line);
        }

        .stTabs [data-baseweb="tab"] {
            padding: 0.65rem 0.85rem;
            border-radius: 7px 7px 0 0;
            font-weight: 650;
            background: transparent;
            color: var(--muted-ink) !important;
        }

        .stTabs [aria-selected="true"] {
            color: var(--accent) !important;
            border-bottom-color: var(--accent) !important;
        }

        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.8rem 0.95rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.92);
        }

        [data-testid="stAppViewContainer"] input,
        [data-testid="stAppViewContainer"] textarea,
        [data-testid="stAppViewContainer"] [contenteditable="true"] {
            background: #ffffff !important;
            border-color: #b9c4d4 !important;
            color: var(--ink) !important;
            caret-color: var(--ink) !important;
        }

        [data-testid="stAppViewContainer"] textarea::placeholder,
        [data-testid="stAppViewContainer"] input::placeholder {
            color: #7c8797 !important;
            opacity: 1 !important;
        }

        [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
            background: #ffffff !important;
            border-color: #b9c4d4 !important;
            color: var(--ink) !important;
        }

        [data-testid="stAppViewContainer"] [data-baseweb="select"] span,
        [data-testid="stAppViewContainer"] [data-baseweb="select"] svg {
            color: var(--ink) !important;
            fill: var(--ink) !important;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 7px;
            border: 1px solid #b9c4d4;
            font-weight: 650;
            background: #ffffff;
            color: var(--ink) !important;
        }

        .stButton > button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
            color: #ffffff !important;
        }

        textarea {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
            line-height: 1.45;
        }

        div[data-testid="stCodeBlock"] pre {
            border-radius: 8px;
        }

        [data-testid="stSidebar"] {
            background: #111827;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #f7fafc !important;
        }

        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #0b1220 !important;
            border-color: #263244 !important;
            color: #f7fafc !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
            color: #f7fafc !important;
            fill: #f7fafc !important;
        }

        [data-testid="stSidebar"] .stButton > button {
            background: #111827;
            border-color: #465466;
            color: #f7fafc !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_base_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    return cleaned or DEFAULT_API_BASE_URL


def api_url(path: str) -> str:
    base_url = normalize_base_url(st.session_state.api_base_url)
    return f"{base_url}{path if path.startswith('/') else '/' + path}"


def error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase

    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            return "; ".join(str(item) for item in detail)
        if detail is not None:
            return json.dumps(detail, ensure_ascii=True)
        return json.dumps(data, ensure_ascii=True)

    return str(data)


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = REQUEST_TIMEOUT,
) -> Any:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                api_url(path),
                json=payload,
                params=params,
            )
    except httpx.ConnectError as exc:
        raise ApiError(f"Could not connect to {normalize_base_url(st.session_state.api_base_url)}") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The API request timed out.") from exc
    except httpx.HTTPError as exc:
        raise ApiError(str(exc)) from exc

    if response.status_code >= 400:
        raise ApiError(error_message(response), response.status_code)
    if not response.content:
        return None
    return response.json()


def request_multipart(
    method: str,
    path: str,
    *,
    data: dict[str, Any],
    files: dict[str, Any],
    timeout: float = REQUEST_TIMEOUT,
) -> Any:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                api_url(path),
                data=data,
                files=files,
            )
    except httpx.ConnectError as exc:
        raise ApiError(f"Could not connect to {normalize_base_url(st.session_state.api_base_url)}") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The API request timed out.") from exc
    except httpx.HTTPError as exc:
        raise ApiError(str(exc)) from exc

    if response.status_code >= 400:
        raise ApiError(error_message(response), response.status_code)
    if not response.content:
        return None
    return response.json()


def show_api_error(exc: ApiError) -> None:
    prefix = f"API {exc.status_code}: " if exc.status_code else ""
    st.error(f"{prefix}{exc}")


def get_or_default(path: str, default: Any, *, params: dict[str, Any] | None = None) -> Any:
    try:
        return request_json("GET", path, params=params)
    except ApiError:
        return default


def compact(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def short_time(value: str | None) -> str:
    if not value:
        return ""
    return str(value).replace("T", " ")[:19]


def csv_to_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def list_to_csv(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value or "")


def parse_json_object(label: str, value: str, *, allow_empty: bool = False) -> dict[str, Any] | None:
    if not value.strip():
        if allow_empty:
            return None
        raise ValueError(f"{label} cannot be empty.")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return parsed


def as_pretty_json(value: Any) -> str:
    return json.dumps(value or {}, indent=2, ensure_ascii=True)


def thread_label(thread: dict[str, Any]) -> str:
    topic = compact(thread.get("topic") or "Untitled post", 68)
    return f"{topic} | {str(thread.get('thread_id', ''))[:8]}"


def activity_label(activity: dict[str, Any]) -> str:
    creator = activity.get("creator_id") or "creator"
    text = compact(activity.get("raw_text"), 74)
    posted = activity.get("posted_at_text") or short_time(activity.get("fetched_at"))
    return f"{creator} | {posted} | {text}"


def creator_label(creator: dict[str, Any]) -> str:
    creator_id = creator.get("creator_id", "")
    display = creator.get("display_name") or creator_id
    return f"{display} | {creator_id}"


def profile_detail_label(profile: dict[str, Any]) -> str:
    creator_id = profile.get("creator_id", "")
    display = profile.get("name") or creator_id
    headline = compact(profile.get("headline"), 48)
    return " | ".join(part for part in [display, creator_id, headline] if part)


def render_profile_detail(profile: dict[str, Any] | None, *, key_prefix: str) -> None:
    if not profile:
        return

    with st.container(border=True):
        top = st.columns([1.2, 2])
        top[0].metric("Creator", profile.get("name") or profile.get("creator_id") or "")
        top[1].metric("Fetched", short_time(profile.get("fetched_at")))
        st.caption(
            " | ".join(
                item
                for item in [
                    f"Creator ID: {profile.get('creator_id', '')}",
                    f"Source: {profile.get('source', '')}",
                ]
                if item.strip(": ")
            )
        )
        st.text_input(
            "Name",
            value=profile.get("name", ""),
            key=f"{key_prefix}_name_{profile.get('creator_id', '')}",
        )
        st.text_area(
            "Headline",
            value=profile.get("headline", ""),
            height=90,
            key=f"{key_prefix}_headline_{profile.get('creator_id', '')}",
        )
        st.text_area(
            "About",
            value=profile.get("about", ""),
            height=180,
            key=f"{key_prefix}_about_{profile.get('creator_id', '')}",
        )
        experience = profile.get("experience") or []
        st.text_area(
            "Experience",
            value="\n\n".join(str(item) for item in experience),
            height=220,
            key=f"{key_prefix}_experience_{profile.get('creator_id', '')}",
        )
        if profile.get("profile_url"):
            st.link_button("Open LinkedIn profile", profile["profile_url"])


def render_thread(
    thread: dict[str, Any] | None,
    *,
    title: str = "Generated Post",
    key_prefix: str = "thread",
) -> None:
    if not thread:
        return

    key_base = f"{key_prefix}_{thread.get('thread_id', 'latest')}_{thread.get('updated_at', '')}"

    with st.container(border=True):
        top = st.columns([3, 1, 1])
        top[0].subheader(title)
        top[1].metric("Edits", int(thread.get("modification_count") or 0))
        top[2].metric("Model", thread.get("model") or "default")

        meta = [
            f"Thread: {thread.get('thread_id', '')}",
            f"Provider: {thread.get('provider') or 'default'}",
            f"Updated: {short_time(thread.get('updated_at'))}",
        ]
        st.caption(" | ".join(item for item in meta if item.strip(": ")))
        st.text_area(
            "Current post",
            value=thread.get("current_post", ""),
            height=320,
            key=f"{key_base}_current",
        )
        st.download_button(
            "Download post",
            data=thread.get("current_post", ""),
            file_name=f"linkedin-post-{str(thread.get('thread_id', 'post'))[:8]}.txt",
            mime="text/plain",
            key=f"{key_base}_download",
        )


def render_metrics(user_data: dict[str, Any] | None) -> None:
    if not user_data:
        return
    cols = st.columns(4)
    cols[0].metric("Creators", len(user_data.get("creators", [])))
    cols[1].metric("Threads", len(user_data.get("threads", [])))
    cols[2].metric("Activities", len(user_data.get("recent_activities", [])))
    user = user_data.get("user") or {}
    cols[3].metric("Profile", compact((user.get("profile") or {}).get("full_name") or user.get("user_id"), 22))


def render_sidebar() -> tuple[list[dict[str, Any]], dict[str, list[str]], bool]:
    with st.sidebar:
        st.title("Control")
        api_base_input = st.text_input("API base URL", value=st.session_state.api_base_url)
        st.session_state.api_base_url = normalize_base_url(api_base_input)

        healthy = False
        try:
            health = request_json("GET", "/health", timeout=8)
            healthy = health.get("status") == "ok"
            st.success("API online")
        except ApiError as exc:
            st.error("API offline")
            st.caption(str(exc))

        providers = get_or_default("/llms/providers", {})
        users = get_or_default("/users", [], params={"limit": 100}) if healthy else []

        st.divider()
        user_ids = [user.get("user_id", "") for user in users if user.get("user_id")]
        if user_ids:
            current = st.session_state.selected_user_id
            index = user_ids.index(current) if current in user_ids else 0
            selected = st.selectbox("Active user", user_ids, index=index)
            st.session_state.selected_user_id = selected
        else:
            st.session_state.selected_user_id = ""
            st.info("No users loaded.")

        st.divider()
        st.subheader("Provider Check")
        provider_names = list(providers.keys()) or ["gemini", "groq", "claude"]
        provider = st.selectbox("Provider", provider_names)
        model_options = providers.get(provider, [])
        model = st.selectbox("Model", model_options or [""])
        api_key = st.text_input("API key", type="password")
        if st.button("Test key", disabled=not api_key.strip(), width="stretch"):
            try:
                result = request_json(
                    "POST",
                    "/llms/test-key",
                    payload={"provider": provider, "model": model, "api_key": api_key},
                    timeout=60,
                )
                if result.get("ok"):
                    st.success(result.get("message") or "Key works.")
                else:
                    st.warning(result.get("message") or "Key test failed.")
            except ApiError as exc:
                show_api_error(exc)

    return users, providers, healthy


def render_profile_tab(users: list[dict[str, Any]], selected_user_id: str) -> None:
    st.subheader("Profile")

    selected_user = next((user for user in users if user.get("user_id") == selected_user_id), None)
    edit_col, create_col = st.columns([1.25, 1])

    with edit_col:
        with st.container(border=True):
            st.markdown("**Edit Active User**")
            if not selected_user:
                st.info("Select or create a user.")
            else:
                profile = dict(selected_user.get("profile") or {})
                writing_style = selected_user.get("writing_style") or {}
                with st.form("update_profile_form"):
                    full_name = st.text_input("Full name", value=str(profile.get("full_name", "")))
                    headline = st.text_input("Headline", value=str(profile.get("headline", "")))
                    location = st.text_input("Location", value=str(profile.get("location", "")))
                    skills = st.text_input("Skills", value=list_to_csv(profile.get("skills")))
                    industries = st.text_input("Industries", value=list_to_csv(profile.get("industries")))
                    experience_summary = st.text_area(
                        "Experience summary",
                        value=str(profile.get("experience_summary", "")),
                        height=140,
                    )
                    writing_style_text = st.text_area(
                        "Writing style JSON",
                        value=as_pretty_json(writing_style),
                        height=220,
                    )
                    submitted = st.form_submit_button("Save profile", type="primary")

                if submitted:
                    try:
                        updated_profile = dict(profile)
                        updated_profile.update(
                            {
                                "full_name": full_name.strip(),
                                "headline": headline.strip(),
                                "location": location.strip(),
                                "skills": csv_to_list(skills),
                                "industries": csv_to_list(industries),
                                "experience_summary": experience_summary.strip(),
                            }
                        )
                        parsed_style = parse_json_object("Writing style JSON", writing_style_text)
                        request_json(
                            "PATCH",
                            f"/users/{selected_user_id}",
                            payload={"profile": updated_profile, "writing_style": parsed_style},
                        )
                        st.success("Profile saved.")
                    except (ApiError, ValueError, json.JSONDecodeError) as exc:
                        st.error(str(exc))

    with create_col:
        with st.container(border=True):
            st.markdown("**Create User**")
            with st.form("create_user_form"):
                new_user_id = st.text_input("User ID", placeholder="new-user")
                new_name = st.text_input("Full name", placeholder="Your name")
                new_headline = st.text_input("Headline", placeholder="AI workflow builder")
                new_location = st.text_input("Location", placeholder="Karachi, Pakistan")
                new_skills = st.text_input("Skills", placeholder="Python, FastAPI, LinkedIn")
                new_industries = st.text_input("Industries", placeholder="AI, software")
                new_summary = st.text_area("Experience summary", height=120)
                new_style_text = st.text_area("Writing style JSON", value="", height=130)
                created = st.form_submit_button("Create user", type="primary")

            if created:
                try:
                    if not new_user_id.strip():
                        raise ValueError("User ID is required.")
                    payload = {
                        "user_id": new_user_id.strip(),
                        "profile": {
                            "full_name": new_name.strip() or new_user_id.strip().replace("-", " ").title(),
                            "headline": new_headline.strip(),
                            "location": new_location.strip(),
                            "skills": csv_to_list(new_skills),
                            "industries": csv_to_list(new_industries),
                            "experience_summary": new_summary.strip(),
                        },
                        "writing_style": parse_json_object(
                            "Writing style JSON",
                            new_style_text,
                            allow_empty=True,
                        ),
                    }
                    created_user = request_json("POST", "/users", payload=payload)
                    st.session_state.selected_user_id = created_user.get("user_id", new_user_id.strip())
                    st.success("User created.")
                except (ApiError, ValueError, json.JSONDecodeError) as exc:
                    st.error(str(exc))


def render_generate_tab(selected_user_id: str, styles: list[str]) -> None:
    st.subheader("Generate")
    if not selected_user_id:
        st.info("Create a user before generating posts.")
        return

    with st.container(border=True):
        with st.form("generate_post_form"):
            idea = st.text_area(
                "Idea",
                placeholder="Write about the practical lesson your audience should remember.",
                height=180,
            )
            style_options = styles or ["Create a post about a topic"]
            generation_style = st.selectbox("Generation style", style_options)
            topic_source = st.selectbox("Topic source", ["manual", "brainstorm", "creator_activity", "research"])
            submitted = st.form_submit_button("Generate post", type="primary")

        if submitted:
            if not idea.strip():
                st.warning("Add an idea first.")
            else:
                try:
                    with st.spinner("Generating post..."):
                        thread = request_json(
                            "POST",
                            "/posts/generate",
                            payload={
                                "user_id": selected_user_id,
                                "idea": idea.strip(),
                                "generation_style": generation_style,
                                "topic_source": topic_source,
                            },
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_thread = thread
                    st.success("Post generated.")
                except ApiError as exc:
                    show_api_error(exc)

    render_thread(st.session_state.last_thread, key_prefix="generate_latest")


def render_modify_tab(selected_user_id: str) -> None:
    st.subheader("Modify")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    threads = get_or_default(f"/users/{selected_user_id}/threads", [], params={"limit": 100})
    if not threads:
        st.info("No generated posts yet.")
        return

    selected_thread = st.selectbox("Thread", threads, format_func=thread_label)
    thread_id = selected_thread.get("thread_id", "")
    thread = None
    if thread_id:
        try:
            thread = request_json("GET", f"/users/{selected_user_id}/threads/{thread_id}")
        except ApiError as exc:
            show_api_error(exc)

    render_thread(thread, title="Current Draft", key_prefix="modify_current")

    with st.container(border=True):
        with st.form("modify_post_form"):
            modification_message = st.text_area(
                "Revision request",
                placeholder="Make it sharper, add a stronger hook, and keep the ending practical.",
                height=150,
            )
            submitted = st.form_submit_button("Apply revision", type="primary")

        if submitted:
            if not modification_message.strip():
                st.warning("Add a revision request.")
            else:
                try:
                    with st.spinner("Revising post..."):
                        updated = request_json(
                            "POST",
                            "/posts/modify",
                            payload={
                                "user_id": selected_user_id,
                                "thread_id": thread_id,
                                "modification_message": modification_message.strip(),
                            },
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_thread = updated
                    st.success("Revision saved.")
                    render_thread(updated, title="Revised Draft", key_prefix="modify_revised")
                except ApiError as exc:
                    show_api_error(exc)


def render_ideas_tab(selected_user_id: str, actions: list[str]) -> None:
    st.subheader("Ideas")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    action_options = actions or ["Brainstorm post topics"]
    default_index = action_options.index("Brainstorm post topics") if "Brainstorm post topics" in action_options else 0

    with st.container(border=True):
        with st.form("brainstorm_form"):
            action = st.selectbox("Action", action_options, index=default_index)
            topic = st.text_input("Topic", placeholder="AI agents for small teams")
            submitted = st.form_submit_button("Brainstorm", type="primary")

        if submitted:
            try:
                with st.spinner("Finding angles..."):
                    result = request_json(
                        "POST",
                        "/ideas/brainstorm",
                        payload={
                            "user_id": selected_user_id,
                            "topic": topic.strip() or None,
                            "action": action,
                        },
                        timeout=LONG_REQUEST_TIMEOUT,
                    )
                st.session_state.last_brainstorm = result
                st.success("Ideas ready.")
            except ApiError as exc:
                show_api_error(exc)

    result = st.session_state.last_brainstorm
    if not result:
        return

    st.caption(
        " | ".join(
            item
            for item in [
                f"Action: {result.get('action', '')}",
                f"Topic: {result.get('topic', '')}",
                f"Model: {result.get('model', '')}",
            ]
            if item.strip(": ")
        )
    )

    for index, idea in enumerate(result.get("ideas", []), start=1):
        with st.container(border=True):
            st.markdown(f"**{index}. {idea.get('title', 'Untitled idea')}**")
            if idea.get("summary"):
                st.write(idea["summary"])
            if idea.get("post_angle"):
                st.info(idea["post_angle"])
            if idea.get("source_url"):
                st.link_button("Open source", idea["source_url"])

            generate_key = f"generate_idea_{index}_{compact(idea.get('title'), 20)}"
            if st.button("Generate from this idea", key=generate_key):
                idea_text = "\n\n".join(
                    part
                    for part in [
                        idea.get("title", ""),
                        idea.get("summary", ""),
                        idea.get("post_angle", ""),
                    ]
                    if part
                )
                try:
                    with st.spinner("Generating post..."):
                        thread = request_json(
                            "POST",
                            "/posts/generate",
                            payload={
                                "user_id": selected_user_id,
                                "idea": idea_text,
                                "generation_style": "Create a post about a topic",
                                "topic_source": "brainstorm",
                            },
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_thread = thread
                    st.success("Post generated from idea.")
                    render_thread(thread, key_prefix=f"ideas_generated_{index}")
                except ApiError as exc:
                    show_api_error(exc)

    suggestions = result.get("research_suggestions") or []
    if suggestions:
        with st.expander("Research suggestions"):
            for suggestion in suggestions:
                st.write(f"- {suggestion}")


def render_creators_tab(selected_user_id: str, user_data: dict[str, Any] | None) -> None:
    st.subheader("Creators")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    creators = (user_data or {}).get("creators") or get_or_default(
        f"/users/{selected_user_id}/creators",
        [],
        params={"limit": 100},
    )

    add_col, scrape_col = st.columns([1, 1.35])

    with add_col:
        with st.container(border=True):
            st.markdown("**Track Creator**")
            with st.form("add_creator_form"):
                profile_url = st.text_input(
                    "LinkedIn profile URL",
                    placeholder="https://www.linkedin.com/in/example/",
                )
                submitted = st.form_submit_button("Add creator", type="primary")

            if submitted:
                try:
                    if not profile_url.strip():
                        raise ValueError("Profile URL is required.")
                    creator = request_json(
                        "POST",
                        "/creators",
                        payload={"user_id": selected_user_id, "profile_url": profile_url.strip()},
                    )
                    st.success(f"Tracking {creator.get('creator_id', 'creator')}.")
                except (ApiError, ValueError) as exc:
                    st.error(str(exc))

    with scrape_col:
        with st.container(border=True):
            st.markdown("**Check Activity**")
            creator_ids = [creator.get("creator_id", "") for creator in creators if creator.get("creator_id")]
            selected_creator_ids = st.multiselect("Creators", creator_ids, default=creator_ids[: min(3, len(creator_ids))])
            max_posts = st.slider("Posts per creator", min_value=1, max_value=20, value=5)
            if st.button("Check for new posts", type="primary", disabled=not creator_ids):
                try:
                    with st.spinner("Checking creators..."):
                        result = request_json(
                            "POST",
                            "/creators/scrape",
                            payload={
                                "user_id": selected_user_id,
                                "creator_ids": selected_creator_ids or None,
                                "max_posts": max_posts,
                            },
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_scrape = result
                    new_count = len(result.get("new_activities", []))
                    st.success(f"Found {new_count} new activities.")
                except ApiError as exc:
                    show_api_error(exc)

    if st.session_state.last_scrape:
        result = st.session_state.last_scrape
        with st.container(border=True):
            st.markdown("**Latest Check**")
            st.caption(f"Checked: {', '.join(result.get('checked_creator_ids', []))}")
            if result.get("errors"):
                st.warning("Some creators returned errors.")
                st.dataframe(result["errors"], width="stretch", hide_index=True)
            if result.get("new_activities"):
                st.dataframe(
                    [
                        {
                            "creator": item.get("creator_id"),
                            "posted": item.get("posted_at_text"),
                            "text": compact(item.get("raw_text"), 120),
                            "url": item.get("post_url"),
                        }
                        for item in result["new_activities"]
                    ],
                    width="stretch",
                    hide_index=True,
                )

    st.markdown("**Tracked Creators**")
    if not creators:
        st.info("No creators tracked.")
        return

    st.dataframe(
        [
            {
                "creator_id": creator.get("creator_id"),
                "display_name": creator.get("display_name"),
                "seen_count": creator.get("seen_count", 0),
                "new_count": creator.get("new_count", 0),
                "last_checked": short_time(creator.get("last_checked_at")),
                "profile_url": creator.get("profile_url"),
            }
            for creator in creators
        ],
        width="stretch",
        hide_index=True,
    )

    delete_col, _ = st.columns([1, 2])
    with delete_col:
        creator_to_delete = st.selectbox("Delete creator", creators, format_func=creator_label)
        if st.button("Delete selected creator", disabled=not creators):
            try:
                request_json(
                    "DELETE",
                    f"/users/{selected_user_id}/creators/{creator_to_delete.get('creator_id')}",
                )
                st.success("Creator deleted.")
            except ApiError as exc:
                show_api_error(exc)


def render_bulk_import_tab(selected_user_id: str) -> None:
    st.subheader("Bulk Import")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Creator sheet",
            type=["csv", "txt", "xlsx"],
            accept_multiple_files=False,
        )
        if st.button("Import creators", type="primary", disabled=uploaded_file is None):
            if uploaded_file is None:
                st.warning("Upload a creator sheet first.")
            else:
                try:
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type or "application/octet-stream",
                        )
                    }
                    with st.spinner("Importing creators..."):
                        result = request_multipart(
                            "POST",
                            "/creators/import",
                            data={"user_id": selected_user_id},
                            files=files,
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_bulk_import = result
                    st.success(f"Imported {len(result.get('added_creators', []))} creator(s).")
                except ApiError as exc:
                    show_api_error(exc)

    result = st.session_state.last_bulk_import
    if not result:
        return

    cols = st.columns(5)
    cols[0].metric("Parsed URLs", result.get("total_urls", 0))
    cols[1].metric("Added", len(result.get("added_creators", [])))
    cols[2].metric("Existing", len(result.get("skipped_existing_creator_ids", [])))
    cols[3].metric("File duplicates", len(result.get("skipped_duplicate_creator_ids", [])))
    cols[4].metric("Errors", len(result.get("errors", [])))

    if result.get("added_creators"):
        st.markdown("**Added Creators**")
        st.dataframe(
            [
                {
                    "creator_id": creator.get("creator_id"),
                    "display_name": creator.get("display_name"),
                    "profile_url": creator.get("profile_url"),
                    "added_at": short_time(creator.get("added_at")),
                }
                for creator in result["added_creators"]
            ],
            width="stretch",
            hide_index=True,
        )

    skipped_rows = [
        {"type": "already tracked", "creator_id": creator_id}
        for creator_id in result.get("skipped_existing_creator_ids", [])
    ] + [
        {"type": "duplicate in file", "creator_id": creator_id}
        for creator_id in result.get("skipped_duplicate_creator_ids", [])
    ]
    if skipped_rows:
        st.markdown("**Skipped**")
        st.dataframe(skipped_rows, width="stretch", hide_index=True)

    if result.get("errors"):
        st.markdown("**Import Errors**")
        st.dataframe(result["errors"], width="stretch", hide_index=True)


def render_profile_scrape_tab(selected_user_id: str, user_data: dict[str, Any] | None) -> None:
    st.subheader("Profile Scrape")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    creators = (user_data or {}).get("creators") or get_or_default(
        f"/users/{selected_user_id}/creators",
        [],
        params={"limit": 100},
    )
    creator_ids = [creator.get("creator_id", "") for creator in creators if creator.get("creator_id")]

    with st.container(border=True):
        selected_creator_ids = st.multiselect(
            "Creators",
            creator_ids,
            default=creator_ids[: min(3, len(creator_ids))],
            key="profile_scrape_creators",
        )
        if st.button("Scrape profile details", type="primary", disabled=not creator_ids):
            try:
                with st.spinner("Scraping creator profile details..."):
                    result = request_json(
                        "POST",
                        "/creators/profile-details/scrape",
                        payload={
                            "user_id": selected_user_id,
                            "creator_ids": selected_creator_ids or None,
                        },
                        timeout=LONG_REQUEST_TIMEOUT,
                    )
                st.session_state.last_profile_scrape = result
                st.success(f"Scraped {len(result.get('profiles', []))} creator profile(s).")
            except ApiError as exc:
                show_api_error(exc)

    result = st.session_state.last_profile_scrape
    if not result:
        return

    with st.container(border=True):
        st.markdown("**Latest Profile Scrape**")
        st.caption(f"Checked: {', '.join(result.get('checked_creator_ids', []))}")
        if result.get("errors"):
            st.warning("Some creators returned errors.")
            st.dataframe(result["errors"], width="stretch", hide_index=True)

        profiles = result.get("profiles", [])
        if profiles:
            st.dataframe(
                [
                    {
                        "creator": item.get("creator_id"),
                        "name": item.get("name"),
                        "headline": compact(item.get("headline"), 100),
                        "about": compact(item.get("about"), 120),
                        "experience_count": len(item.get("experience") or []),
                        "fetched": short_time(item.get("fetched_at")),
                    }
                    for item in profiles
                ],
                width="stretch",
                hide_index=True,
            )
            selected_profile = st.selectbox("Scraped profile", profiles, format_func=profile_detail_label)
            render_profile_detail(selected_profile, key_prefix="profile_scrape_detail")


def render_creator_details_tab(selected_user_id: str) -> None:
    st.subheader("Creator Details")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    with st.container(border=True):
        cols = st.columns([1, 1, 2])
        limit = cols[0].number_input(
            "Limit",
            min_value=1,
            max_value=500,
            value=100,
            step=10,
            key="creator_profile_details_limit",
        )
        if cols[1].button("Load all details", type="primary"):
            try:
                result = request_json(
                    "GET",
                    f"/users/{selected_user_id}/creators/profile-details",
                    params={"limit": int(limit)},
                )
                st.session_state.last_creator_profile_details = result
                st.success(f"Loaded {len(result)} creator detail record(s).")
            except ApiError as exc:
                show_api_error(exc)

    profiles = st.session_state.last_creator_profile_details or []
    if profiles:
        st.dataframe(
            [
                {
                    "creator": item.get("creator_id"),
                    "name": item.get("name"),
                    "headline": compact(item.get("headline"), 100),
                    "fetched": short_time(item.get("fetched_at")),
                    "profile_url": item.get("profile_url"),
                }
                for item in profiles
            ],
            width="stretch",
            hide_index=True,
        )

        selected_profile = st.selectbox("Creator profile", profiles, format_func=profile_detail_label)
        if st.button("Fetch selected creator details"):
            try:
                specific = request_json(
                    "GET",
                    f"/users/{selected_user_id}/creators/{selected_profile.get('creator_id')}/profile-details",
                )
                st.session_state.last_specific_creator_profile = specific
                st.success("Creator details loaded.")
            except ApiError as exc:
                show_api_error(exc)

        render_profile_detail(
            st.session_state.last_specific_creator_profile or selected_profile,
            key_prefix="creator_details_saved",
        )
    else:
        st.info("No creator profile details loaded yet.")


def render_recent_scrape_tab(selected_user_id: str, user_data: dict[str, Any] | None) -> None:
    st.subheader("24h Scrape")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    creators = (user_data or {}).get("creators") or get_or_default(
        f"/users/{selected_user_id}/creators",
        [],
        params={"limit": 100},
    )
    creator_ids = [creator.get("creator_id", "") for creator in creators if creator.get("creator_id")]

    with st.container(border=True):
        selected_creator_ids = st.multiselect(
            "Creators",
            creator_ids,
            default=creator_ids[: min(3, len(creator_ids))],
            key="recent_scrape_creators",
        )
        max_posts = st.slider(
            "Posts per creator",
            min_value=1,
            max_value=20,
            value=5,
            key="recent_scrape_max_posts",
        )
        window_hours = st.slider(
            "Window hours",
            min_value=1,
            max_value=168,
            value=24,
            key="recent_scrape_window_hours",
        )
        if st.button("Check recent posts", type="primary", disabled=not creator_ids):
            try:
                with st.spinner("Checking recent creator posts..."):
                    result = request_json(
                        "POST",
                        "/creators/scrape/recent-24h",
                        payload={
                            "user_id": selected_user_id,
                            "creator_ids": selected_creator_ids or None,
                            "max_posts": max_posts,
                            "window_hours": window_hours,
                        },
                        timeout=LONG_REQUEST_TIMEOUT,
                    )
                st.session_state.last_recent_scrape = result
                st.success(f"Found {len(result.get('activities', []))} recent activities.")
            except ApiError as exc:
                show_api_error(exc)

    result = st.session_state.last_recent_scrape
    if not result:
        return

    with st.container(border=True):
        st.markdown("**Latest 24h Check**")
        st.caption(
            " | ".join(
                item
                for item in [
                    f"Window: {result.get('window_hours', 24)}h",
                    f"Checked: {', '.join(result.get('checked_creator_ids', []))}",
                ]
                if item.strip(": ")
            )
        )
        if result.get("errors"):
            st.warning("Some creators returned errors.")
            st.dataframe(result["errors"], width="stretch", hide_index=True)
        activities = result.get("activities", [])
        if activities:
            st.dataframe(
                [
                    {
                        "creator": item.get("creator_id"),
                        "posted": item.get("posted_at_text"),
                        "new_in_db": item.get("is_new", False),
                        "text": compact(item.get("raw_text"), 130),
                        "url": item.get("post_url"),
                    }
                    for item in activities
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No posts matched the selected time window.")


def render_recent_db_tab(selected_user_id: str) -> None:
    st.subheader("24h Saved")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    with st.container(border=True):
        cols = st.columns([1, 1, 2])
        window_hours = cols[0].slider(
            "Window hours",
            min_value=1,
            max_value=168,
            value=24,
            key="recent_db_window_hours",
        )
        limit = cols[1].number_input(
            "Limit",
            min_value=1,
            max_value=500,
            value=100,
            step=10,
            key="recent_db_limit",
        )
        if cols[2].button("Load saved recent posts", type="primary"):
            try:
                result = request_json(
                    "GET",
                    f"/users/{selected_user_id}/activities/recent-24h",
                    params={"limit": int(limit), "window_hours": int(window_hours)},
                )
                st.session_state.last_recent_db_activities = result
                st.success(f"Loaded {len(result.get('activities', []))} saved activities.")
            except ApiError as exc:
                show_api_error(exc)

    result = st.session_state.last_recent_db_activities
    if not result:
        return

    activities = result.get("activities", [])
    st.caption(f"Window: {result.get('window_hours', 24)}h | Saved activities: {len(activities)}")
    if not activities:
        st.info("No saved posts matched the selected time window.")
        return

    st.dataframe(
        [
            {
                "creator": item.get("creator_id"),
                "posted": item.get("posted_at_text"),
                "fetched": short_time(item.get("fetched_at")),
                "new_in_db": item.get("is_new", False),
                "text": compact(item.get("raw_text"), 130),
                "url": item.get("post_url"),
            }
            for item in activities
        ],
        width="stretch",
        hide_index=True,
    )

    selected_activity = st.selectbox("Saved recent activity", activities, format_func=activity_label)
    with st.container(border=True):
        st.caption(
            " | ".join(
                item
                for item in [
                    f"Creator: {selected_activity.get('creator_id')}",
                    f"Post: {compact(selected_activity.get('post_id'), 36)}",
                    f"Fetched: {short_time(selected_activity.get('fetched_at'))}",
                ]
                if item.strip(": ")
            )
        )
        st.text_area(
            "Saved creator post",
            value=selected_activity.get("raw_text", ""),
            height=260,
            key=f"recent_db_text_{selected_activity.get('creator_id')}_{selected_activity.get('post_id')}",
        )
        if selected_activity.get("post_url"):
            st.link_button("Open LinkedIn post", selected_activity["post_url"])


def render_activity_tab(selected_user_id: str, user_data: dict[str, Any] | None) -> None:
    st.subheader("Activity")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    activities = (user_data or {}).get("recent_activities") or get_or_default(
        f"/users/{selected_user_id}/activities",
        [],
        params={"limit": 100},
    )
    if not activities:
        st.info("No creator activity yet.")
        return

    st.dataframe(
        [
            {
                "creator": item.get("creator_id"),
                "posted": item.get("posted_at_text") or short_time(item.get("fetched_at")),
                "new": item.get("is_new", False),
                "text": compact(item.get("raw_text"), 130),
                "url": item.get("post_url"),
            }
            for item in activities
        ],
        width="stretch",
        hide_index=True,
    )

    selected_activity = st.selectbox("Activity", activities, format_func=activity_label)
    with st.container(border=True):
        st.caption(
            " | ".join(
                item
                for item in [
                    f"Creator: {selected_activity.get('creator_id')}",
                    f"Post: {compact(selected_activity.get('post_id'), 36)}",
                    f"Fetched: {short_time(selected_activity.get('fetched_at'))}",
                ]
                if item.strip(": ")
            )
        )
        st.text_area(
            "Creator post",
            value=selected_activity.get("raw_text", ""),
            height=260,
            key=f"activity_text_{selected_activity.get('creator_id')}_{selected_activity.get('post_id')}",
        )
        if selected_activity.get("post_url"):
            st.link_button("Open LinkedIn post", selected_activity["post_url"])

        if st.button("Generate post from this activity", type="primary"):
            try:
                with st.spinner("Generating inspired post..."):
                    thread = request_json(
                        "POST",
                        "/posts/from-creator-activity",
                        payload={
                            "user_id": selected_user_id,
                            "creator_id": selected_activity.get("creator_id"),
                            "post_id": selected_activity.get("post_id"),
                        },
                        timeout=LONG_REQUEST_TIMEOUT,
                    )
                st.session_state.last_activity_thread = thread
                st.session_state.last_thread = thread
                st.success("Post generated from activity.")
            except ApiError as exc:
                show_api_error(exc)

    render_thread(
        st.session_state.last_activity_thread,
        title="Activity-Based Draft",
        key_prefix="activity_generated",
    )


def render_comments_tab(
    selected_user_id: str,
    user_data: dict[str, Any] | None,
    comment_topics: list[str],
) -> None:
    st.subheader("Comments")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    activities = (user_data or {}).get("recent_activities") or get_or_default(
        f"/users/{selected_user_id}/activities",
        [],
        params={"limit": 100},
    )
    if not activities:
        st.info("No creator activity yet.")
        return

    selected_activity = st.selectbox("Activity for comment", activities, format_func=activity_label)
    comment_topic = st.selectbox("Comment angle", comment_topics or ["Add Value"])

    left, right = st.columns([1.1, 1])
    with left:
        with st.container(border=True):
            st.markdown("**Creator Post**")
            st.text_area(
                "Post text",
                value=selected_activity.get("raw_text", ""),
                height=260,
                key=f"comment_activity_{selected_activity.get('creator_id')}_{selected_activity.get('post_id')}",
            )
            if st.button("Generate comment", type="primary"):
                try:
                    with st.spinner("Generating comment..."):
                        comment = request_json(
                            "POST",
                            "/comments/generate",
                            payload={
                                "user_id": selected_user_id,
                                "creator_id": selected_activity.get("creator_id"),
                                "post_id": selected_activity.get("post_id"),
                                "comment_topic": comment_topic,
                            },
                            timeout=LONG_REQUEST_TIMEOUT,
                        )
                    st.session_state.last_comment = comment
                    st.success("Comment generated.")
                except ApiError as exc:
                    show_api_error(exc)

    with right:
        with st.container(border=True):
            st.markdown("**Prepared Comment**")
            comment = st.session_state.last_comment or {}
            comment_text = st.text_area(
                "Comment",
                value=comment.get("comment", ""),
                height=180,
                key=f"prepared_comment_{comment.get('generated_at', 'empty')}",
            )
            if comment:
                st.caption(
                    " | ".join(
                        item
                        for item in [
                            f"Topic: {comment.get('comment_topic', '')}",
                            f"Model: {comment.get('model', '')}",
                            f"Generated: {short_time(comment.get('generated_at'))}",
                        ]
                        if item.strip(": ")
                    )
                )
            if st.button("Mark as commented", disabled=not comment_text.strip()):
                try:
                    marked = request_json(
                        "PATCH",
                        "/comments/mark",
                        payload={
                            "user_id": selected_user_id,
                            "creator_id": selected_activity.get("creator_id"),
                            "post_id": selected_activity.get("post_id"),
                            "commented": True,
                            "comment_text": comment_text.strip(),
                        },
                    )
                    st.session_state.last_comment = marked
                    st.success("Marked as commented.")
                except ApiError as exc:
                    show_api_error(exc)

    commented = get_or_default(
        f"/users/{selected_user_id}/engagements/comments",
        [],
        params={"limit": 50},
    )
    if commented:
        st.markdown("**Commented Activity**")
        st.dataframe(
            [
                {
                    "creator": item.get("creator_id"),
                    "topic": item.get("comment_topic"),
                    "comment": compact(item.get("comment"), 120),
                    "commented_at": short_time(item.get("commented_at")),
                    "post": compact(item.get("raw_text"), 120),
                }
                for item in commented
            ],
            width="stretch",
            hide_index=True,
        )


def render_history_tab(selected_user_id: str) -> None:
    st.subheader("History")
    if not selected_user_id:
        st.info("Select a user first.")
        return

    threads = get_or_default(f"/users/{selected_user_id}/threads", [], params={"limit": 100})
    if not threads:
        st.info("No generated posts yet.")
        return

    st.dataframe(
        [
            {
                "thread_id": item.get("thread_id"),
                "topic": compact(item.get("topic"), 120),
                "source": item.get("topic_source"),
                "style": item.get("generation_style"),
                "updated": short_time(item.get("updated_at")),
            }
            for item in threads
        ],
        width="stretch",
        hide_index=True,
    )

    selected_thread = st.selectbox("Open thread", threads, format_func=thread_label)
    thread_id = selected_thread.get("thread_id", "")
    thread = None
    if thread_id:
        try:
            thread = request_json("GET", f"/users/{selected_user_id}/threads/{thread_id}")
        except ApiError as exc:
            show_api_error(exc)

    if thread:
        render_thread(thread, title="Saved Draft", key_prefix="history_saved")
        with st.expander("Original post"):
            st.text_area(
                "Original",
                value=thread.get("original_post", ""),
                height=260,
                key=f"original_{thread_id}",
            )
        with st.expander("Conversation"):
            st.json(thread.get("conversation", []))

        if st.button("Delete thread"):
            try:
                request_json("DELETE", f"/users/{selected_user_id}/threads/{thread_id}")
                st.success("Thread deleted.")
            except ApiError as exc:
                show_api_error(exc)


def main() -> None:
    st.set_page_config(
        page_title="LinkedIn Post Generator",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_styles()

    users, _providers, healthy = render_sidebar()

    st.title("LinkedIn Post Generator")
    st.caption(f"Backend: {normalize_base_url(st.session_state.api_base_url)}")

    selected_user_id = st.session_state.selected_user_id
    user_data = None
    if healthy and selected_user_id:
        try:
            user_data = request_json(
                "GET",
                f"/users/{selected_user_id}/data",
                params={"limit": 100},
            )
        except ApiError as exc:
            show_api_error(exc)

    render_metrics(user_data)

    actions = get_or_default("/actions", []) if healthy else []
    styles = get_or_default("/post-generation-styles", []) if healthy else []
    comment_topics = get_or_default("/comments/topics", []) if healthy else []

    tabs = st.tabs(
        [
            "Generate",
            "Ideas",
            "Modify",
            "Creators",
            "Bulk Import",
            "Profile Scrape",
            "Creator Details",
            "24h Scrape",
            "24h Saved",
            "Activity",
            "Comments",
            "History",
            "Profile",
        ]
    )

    with tabs[0]:
        render_generate_tab(selected_user_id, styles)
    with tabs[1]:
        render_ideas_tab(selected_user_id, actions)
    with tabs[2]:
        render_modify_tab(selected_user_id)
    with tabs[3]:
        render_creators_tab(selected_user_id, user_data)
    with tabs[4]:
        render_bulk_import_tab(selected_user_id)
    with tabs[5]:
        render_profile_scrape_tab(selected_user_id, user_data)
    with tabs[6]:
        render_creator_details_tab(selected_user_id)
    with tabs[7]:
        render_recent_scrape_tab(selected_user_id, user_data)
    with tabs[8]:
        render_recent_db_tab(selected_user_id)
    with tabs[9]:
        render_activity_tab(selected_user_id, user_data)
    with tabs[10]:
        render_comments_tab(selected_user_id, user_data, comment_topics)
    with tabs[11]:
        render_history_tab(selected_user_id)
    with tabs[12]:
        render_profile_tab(users, selected_user_id)


if __name__ == "__main__":
    main()
