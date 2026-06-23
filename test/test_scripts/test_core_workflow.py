from __future__ import annotations

import json
from pathlib import Path

from app.extract_resume_details import extract_resume_profile
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.llms.llm_structure_schema import GeneratedPost
from app.nodes import post_nodes
from app.travily_tool import build_post_search_queries
from app.writing_style_extract import builtin_writing_styles, extract_writing_style

ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = ROOT / "test" / "test_data"
TEST_RESPONSES = ROOT / "test" / "test_responses"


def _read_text(name: str) -> str:
    return (TEST_DATA / name).read_text(encoding="utf-8")


def _read_json(name: str) -> dict:
    return json.loads((TEST_RESPONSES / name).read_text(encoding="utf-8"))


def test_builtin_styles_are_available() -> None:
    styles = builtin_writing_styles()
    assert len(styles) == 3
    assert {style.name for style in styles} == {"Clear Builder", "Story Driven", "Research Analyst"}


def test_extract_writing_style_offline() -> None:
    expected = _read_json("expected_writing_style.json")
    style = extract_writing_style(_read_text("sample_previous_post.txt"))
    assert style.name == expected["name"]
    assert style.confidence >= expected["minimum_confidence"]
    assert expected["required_hashtag"] in style.hashtags


def test_extract_resume_profile_offline() -> None:
    profile = extract_resume_profile(_read_text("sample_resume.txt"))
    assert profile.full_name == "Mughees Khan"
    assert "Python" in profile.skills
    assert profile.links


def test_local_storage_lifecycle(tmp_path, monkeypatch) -> None:
    import app.storage as storage

    monkeypatch.setattr(storage, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(storage, "SESSION_INDEX_PATH", tmp_path / "sessions_index.json")

    record = storage.create_session("groq", "llama-3.3-70b-versatile")
    assert record["chat_name"] == "chat1"
    assert record["step"] == "writing_style"

    updated = storage.update_session(record["session_id"], step="resume", writing_style={"tone": "clear"})
    assert updated["step"] == "resume"

    loaded = storage.load_session(record["session_id"])
    assert loaded is not None
    assert loaded["writing_style"]["tone"] == "clear"

    sessions = storage.list_sessions()
    assert sessions[0]["chat_name"] == "chat1"


def test_generation_graph_offline() -> None:
    style = extract_writing_style(_read_text("sample_previous_post.txt"))
    profile = extract_resume_profile(_read_text("sample_resume.txt"))
    topic = _read_text("sample_topic.txt")

    result = run_post_generation(
        {
            "workflow_mode": "generate",
            "topic": topic,
            "writing_style": style.model_dump(),
            "resume_profile": profile.model_dump(),
            "messages": [{"role": "user", "content": topic}],
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "api_key": "",
            "attempts": 0,
            "max_attempts": 3,
        }
    )

    assert result["final_post"]
    assert "AI" in result["final_post"] or "writing" in result["final_post"]
    assert result["review_passed"] is True
    assert result["attempts"] <= 3
    assert result["provider"] == "groq"
    assert result["model"] == "llama-3.3-70b-versatile"
    assert len(result["search_queries"]) >= 4
    assert len(result["search_results"]) >= 4


def test_post_search_queries_cover_current_context() -> None:
    queries = build_post_search_queries(
        "caveman and RTK tool in LLM coding",
        "make it current",
        count=4,
    )
    assert len(queries) == 4
    assert any("caveman" in query.lower() for query in queries)
    assert any("rtk" in query.lower() for query in queries)
    assert any("meaning current usage" in query.lower() for query in queries)
    assert any("latest examples" in query for query in queries)


def test_generation_node_does_not_trust_llm_provider_metadata(monkeypatch) -> None:
    def fake_invoke_structured(*args, **kwargs):
        return GeneratedPost(
            post="A researched LinkedIn post with enough detail to pass the node output contract.",
            provider="OpenAI",
            model="gpt-4o",
        )

    monkeypatch.setattr(post_nodes, "invoke_structured", fake_invoke_structured)
    result = post_nodes.generate_post_node(
        {
            "topic": "AI coding",
            "messages": [{"role": "user", "content": "AI coding"}],
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "attempts": 0,
            "max_attempts": 3,
        }
    )
    assert result["provider"] == "groq"
    assert result["model"] == "openai/gpt-oss-120b"


def test_guardrail_blocks_off_topic_chat() -> None:
    expected = _read_json("expected_guardrail.json")
    result = run_post_chat_edit(
        {
            "workflow_mode": "chat",
            "topic": "AI writing",
            "current_post": "AI writing gets better when people review the output before publishing.",
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "api_key": "",
            "attempts": 0,
            "max_attempts": 3,
        }
    )
    assert result["guardrail_reply"] == expected["guardrail_reply"]
    assert result["messages"][-1]["content"] == expected["guardrail_reply"]


def test_research_fallback_needs_details_then_returns_findings() -> None:
    missing = research_trending_topics()
    assert missing.needs_more_user_details is True

    expected = _read_json("expected_research.json")
    results = research_trending_topics(extra_details="Python developer building AI writing apps")
    assert results.needs_more_user_details is expected["needs_more_user_details"]
    assert len(results.findings) >= expected["minimum_findings"]
