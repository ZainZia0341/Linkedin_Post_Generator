from __future__ import annotations

import json
from pathlib import Path

import app.langchain_deep_search as deep_search
from app.deep_research_agent import (
    DeepResearchReport,
    DeepResearchUnavailable,
    build_deep_research_agent,
)
from app.extract_resume_details import extract_resume_profile
from app.graph_state import run_post_chat_edit, run_post_generation
from app.langchain_deep_search import research_trending_topics
from app.llms.llm import LLMConfig
from app.llms.llm_structure_schema import GeneratedPost
from app.llms.llm_structure_schema import ResearchResults
from app.nodes import post_nodes
from app.post_formatting import format_linkedin_post, formatting_issues
from app.travily_tool import build_post_search_queries, search_recent_web
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


def test_recent_web_search_uses_exact_recent_query_without_key() -> None:
    query = "AWS Lambda latest launch release announcement 2026"
    results = search_recent_web(query, max_results=2)
    assert results[0]["query"] == query
    assert "meaning current usage" not in results[0]["query"]


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


def test_format_linkedin_post_splits_wall_of_text() -> None:
    raw_post = (
        "This is a practical lesson about cloud engineering. It starts with a real production problem. "
        "The team needs reliability without making the system harder to operate. A good approach is to "
        "keep the architecture boring where possible. Then use automation only where the workflow repeats. "
        "That balance keeps costs visible and makes incidents easier to debug. #Cloud #Backend"
    )
    formatted = format_linkedin_post(raw_post)
    assert "\n\n" in formatted
    assert formatted.endswith("#Cloud #Backend")
    assert not formatting_issues(formatted)


def test_formatting_issues_reject_wall_of_text() -> None:
    wall_text = " ".join(["This sentence keeps going without any useful paragraph break."] * 12)
    issues = formatting_issues(wall_text)
    assert any("wall of text" in issue for issue in issues)


def test_research_results_accepts_string_boolean() -> None:
    result = ResearchResults.model_validate({"needs_more_user_details": "false", "findings": []})
    assert result.needs_more_user_details is False


def test_research_keyword_extraction_prefers_stack_terms() -> None:
    keywords = deep_search.extract_research_keywords(
        {
            "headline": "Senior Backend & Cloud Engineer",
            "skills": ["Amazon Web Services (AWS)", "AWS Lambda", "Node.js", "TypeScript"],
            "experience_summary": "Built payment orchestration with DynamoDB, EventBridge, LangChain, and AWS Bedrock.",
            "industries": ["fintech"],
        }
    )

    assert "AWS Lambda" in keywords
    assert "DynamoDB" in keywords
    assert "EventBridge" in keywords
    assert "LangChain" in keywords
    assert "Node.js" in keywords
    assert "Senior" not in keywords


def test_research_fallback_plan_uses_recent_launch_queries() -> None:
    keywords = ["AWS Lambda", "DynamoDB", "LangChain", "Node.js", "payments"]
    plan = deep_search._fallback_plan(
        "Senior backend engineer using AWS Lambda, DynamoDB, LangChain, Node.js, and payments.",
        keywords,
    )

    assert len(plan.tasks) >= 3
    assert all(deep_search._has_recency_intent(task.query) for task in plan.tasks)
    assert all("latest" in task.query.lower() or "release" in task.query.lower() for task in plan.tasks)
    assert not any("cold start" in task.query.lower() for task in plan.tasks)


def test_deep_research_agent_requires_keys() -> None:
    config = LLMConfig(provider="groq", model="llama-3.3-70b-versatile", api_key="")
    try:
        build_deep_research_agent(config)
    except DeepResearchUnavailable as exc:
        assert "LLM API key" in str(exc)
    else:
        raise AssertionError("Deep research should require an LLM API key.")


def test_research_uses_official_deep_agent_when_available(monkeypatch) -> None:
    calls: dict[str, str] = {}

    def fake_run_deep_research_agent(request: str, llm_config: LLMConfig) -> DeepResearchReport:
        calls["request"] = request
        return DeepResearchReport(
            request=request,
            report=(
                "## Serverless cost angle\n"
                "AWS teams are focusing on reliability and cost controls. [1]\n\n"
                "### Sources\n"
                "[1] AWS Architecture Blog: https://example.com/aws"
            ),
            provider=llm_config.provider,
            model=llm_config.model,
        )

    def fake_invoke_structured(*args, **kwargs):
        return kwargs["fallback_factory"]()

    monkeypatch.setattr(deep_search.travily_tool, "get_tavily_api_key", lambda: "tvly-test")
    monkeypatch.setattr(deep_search, "run_deep_research_agent", fake_run_deep_research_agent)
    monkeypatch.setattr(deep_search, "invoke_structured", fake_invoke_structured)

    result = research_trending_topics(
        extra_details="Senior backend and cloud engineer focused on AWS serverless",
        llm_config=LLMConfig(
            provider="groq",
            model="llama-3.3-70b-versatile",
            api_key="test-key",
        ),
    )

    assert "Professional context" in calls["request"]
    assert result.provider == "groq"
    assert result.model == "llama-3.3-70b-versatile"
    assert result.findings
    assert result.findings[0].source_url == "https://example.com/aws"


def test_research_labels_fallback_when_deep_agent_fails(monkeypatch) -> None:
    def fake_run_deep_research_agent(request: str, llm_config: LLMConfig) -> DeepResearchReport:
        raise DeepResearchUnavailable("tool_use_failed")

    def fake_invoke_structured(*args, **kwargs):
        return kwargs["fallback_factory"]()

    def fake_search_recent_web(query: str, max_results: int, time_range: str):
        return [
            {
                "title": "Useful source",
                "content": "A concise source-backed snippet about cloud architecture cost and reliability.",
                "url": "https://example.com/source",
                "published_date": "2026-06-01",
            }
        ]

    monkeypatch.setattr(deep_search.travily_tool, "get_tavily_api_key", lambda: "tvly-test")
    monkeypatch.setattr(deep_search, "run_deep_research_agent", fake_run_deep_research_agent)
    monkeypatch.setattr(deep_search, "invoke_structured", fake_invoke_structured)
    monkeypatch.setattr(deep_search, "search_recent_web", fake_search_recent_web)

    result = research_trending_topics(
        extra_details="Senior backend and cloud engineer focused on AWS serverless",
        llm_config=LLMConfig(
            provider="groq",
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key="test-key",
        ),
    )

    assert result.research_engine == "fallback"
    assert "Official Deep Agents unavailable" in result.status_message
    assert result.findings
    assert result.findings[0].title != "Tavily answer"
    assert result.findings[0].source_url == "https://example.com/source"
    assert "2026-06-01" in result.findings[0].recency_signal


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
