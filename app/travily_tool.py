from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import PROJECT_ROOT, TAVILY_SEARCH_RESULTS
from app.llms.llm import LLMConfig, create_chat_model

DEFAULT_POST_SEARCH_COUNT = int(os.getenv("TAVILY_POST_SEARCH_COUNT", "6"))
DEFAULT_RESULTS_PER_QUERY = int(os.getenv("TAVILY_RESULTS_PER_QUERY", "3"))

_GENERIC_QUERY_WORDS = {
    "about",
    "best",
    "better",
    "coding",
    "current",
    "especially",
    "examples",
    "facts",
    "latest",
    "linkedin",
    "meaning",
    "post",
    "practical",
    "recent",
    "software",
    "tool",
    "usage",
    "with",
}


def _read_env_value(key: str) -> str:
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "example.env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or not stripped.startswith(f"{key}="):
                continue
            raw_value = stripped.split("=", 1)[1].strip()
            return raw_value.strip().strip('"').strip("'")
    return ""


def get_tavily_api_key() -> str:
    api_key = os.getenv("TAVILY_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        api_key = _read_env_value("TAVILY_API_KEY")
    if api_key:
        os.environ["TAVILY_API_KEY"] = api_key
    return api_key


def build_tavily_search_tool(max_results: int = DEFAULT_RESULTS_PER_QUERY):
    from langchain_tavily import TavilySearch

    get_tavily_api_key()
    return TavilySearch(
        max_results=max_results,
        search_depth="advanced",
        topic="general",
        include_answer=True,
    )


def _normalize_tavily_result(raw_result: Any, query: str) -> list[dict[str, str]]:
    if isinstance(raw_result, dict):
        items = raw_result.get("results") or []
        answer = raw_result.get("answer")
        normalized = []
        if answer:
            normalized.append(
                {
                    "query": query,
                    "title": "Tavily answer",
                    "content": str(answer),
                    "url": "",
                }
            )
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "query": query,
                        "title": str(item.get("title", "Untitled")),
                        "content": str(item.get("content", item.get("summary", ""))),
                        "url": str(item.get("url", "")),
                    }
                )
        return normalized

    if isinstance(raw_result, str):
        return [{"query": query, "title": "Tavily result", "content": raw_result, "url": ""}]

    if isinstance(raw_result, list):
        normalized = []
        for item in raw_result:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "query": query,
                        "title": str(item.get("title", "Untitled")),
                        "content": str(item.get("content", item.get("summary", ""))),
                        "url": str(item.get("url", "")),
                    }
                )
        return normalized

    return []


def build_post_search_queries(
    topic: str,
    user_message: str = "",
    count: int = DEFAULT_POST_SEARCH_COUNT,
) -> list[str]:
    base_text = " ".join(part.strip() for part in (topic, user_message) if part.strip())
    base_text = base_text or "LinkedIn post topic"
    collapsed = re.sub(r"\s+", " ", base_text).strip()
    context = "LLM coding software development" if re.search(r"\b(llm|coding|code)\b", collapsed, re.I) else "software development"

    focused_terms = _extract_focused_terms(collapsed)
    queries = [f"{collapsed} meaning current usage"]
    for term in focused_terms:
        queries.append(f"{term} meaning current usage in {context}")
        queries.append(f"{term} latest examples in {context}")

    queries.extend(
        [
            f"{collapsed} latest examples explanation",
            f"{collapsed} practical use in {context}",
            f"{collapsed} best practices facts",
        ]
    )
    return _dedupe_queries(queries, count)


def _extract_focused_terms(text: str) -> list[str]:
    lower_text = text.lower()
    terms: list[str] = []

    if "caveman" in lower_text:
        terms.append("caveman prompt LLM coding")
    if re.search(r"\brtk\b", lower_text):
        terms.append("RTK tool coding Redux Toolkit")

    acronym_tokens = re.findall(r"\b[A-Za-z]{2,6}\b", text)
    for token in acronym_tokens:
        lower_token = token.lower()
        if lower_token in {"llm", "ai", "api", "ui", "ux"}:
            continue
        if token.isupper() or lower_token in {"rtk"}:
            terms.append(f"{token.upper()} tool software development")

    words = re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", text)
    for word in words:
        lower_word = word.lower()
        if lower_word in _GENERIC_QUERY_WORDS:
            continue
        if lower_word in {"llm", "rtk"}:
            continue
        terms.append(f"{word} {context_hint(text)}")
        if len(terms) >= 4:
            break

    return _dedupe_terms(terms, 4)


def context_hint(text: str) -> str:
    if re.search(r"\b(llm|prompt|coding|code)\b", text, re.I):
        return "LLM coding"
    return "software development"


def _dedupe_terms(terms: list[str], limit: int) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = re.sub(r"\s+", " ", term).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) == limit:
            break
    return deduped


def _dedupe_queries(queries: list[str], limit: int) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = re.sub(r"\s+", " ", query).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) == limit:
            break
    return deduped


def _tool_call_queries(
    config: LLMConfig,
    tool: Any,
    topic: str,
    user_message: str,
    count: int,
) -> list[str]:
    if not config.resolved_api_key():
        return []

    try:
        print("Planning Tavily searches with LLM tool binding.")
        model = create_chat_model(config).bind_tools([tool])
        message = model.invoke(
            [
                SystemMessage(
                    content=(
                        "You plan web research for LinkedIn post generation. "
                        "Call the tavily_search tool multiple times with precise queries. "
                        "Use one tool call per query. Do not answer directly."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Topic: {topic}\n"
                        f"Latest user request: {user_message}\n"
                        f"Call the Tavily tool exactly {count} times. "
                        "Make separate searches for each distinct concept, acronym, library, or phrase. "
                        "For example, if the request mentions two terms, search both terms separately. "
                        "Clarify current meaning, recent usage, facts, examples, and best practices."
                    )
                ),
            ]
        )
        queries = []
        for call in getattr(message, "tool_calls", []) or []:
            args = call.get("args", {}) if isinstance(call, dict) else {}
            query = args.get("query") or args.get("input")
            if query:
                queries.append(str(query))
        return queries[:count]
    except Exception as exc:
        print(f"LLM Tavily tool planning failed, using fallback queries: {exc}")
        return []


def run_tavily_post_research(
    topic: str,
    llm_config: LLMConfig | None = None,
    user_message: str = "",
    count: int = DEFAULT_POST_SEARCH_COUNT,
    results_per_query: int = DEFAULT_RESULTS_PER_QUERY,
) -> list[dict[str, str]]:
    fallback_queries = build_post_search_queries(topic, user_message, count)
    api_key = get_tavily_api_key()
    if not api_key:
        print("Tavily post research skipped: no TAVILY_API_KEY was found.")
        return [
            {
                "query": query,
                "title": "No live Tavily search",
                "content": "No Tavily API key was available. Verify current facts before publishing.",
                "url": "",
            }
            for query in fallback_queries
        ]

    try:
        tool = build_tavily_search_tool(max_results=results_per_query)
        planned_queries = (
            _tool_call_queries(llm_config, tool, topic, user_message, count)
            if llm_config is not None
            else []
        )
        queries = _dedupe_queries(planned_queries + fallback_queries, count)
        if len(planned_queries) < count:
            print(
                f"LLM planned {len(planned_queries)} Tavily search(es); "
                f"filled to {len(queries)} with deterministic focused queries."
            )
        print(f"Running {len(queries)} Tavily post search(es).")

        all_results: list[dict[str, str]] = []
        seen_keys: set[str] = set()
        for query in queries:
            print(f"Tavily search query: {query}")
            raw_result = tool.invoke({"query": query})
            for result in _normalize_tavily_result(raw_result, query):
                dedupe_key = result.get("url") or f"{result.get('title')}|{result.get('content')[:80]}"
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                all_results.append(result)

        if all_results:
            print(f"Tavily post research collected {len(all_results)} source item(s).")
            return all_results
    except Exception as exc:
        print(f"Tavily post research failed, using fallback search notes: {exc}")

    return [
        {
            "query": query,
            "title": "Tavily search fallback",
            "content": "Live search failed. Verify current facts before publishing.",
            "url": "",
        }
        for query in fallback_queries
    ]


def search_web(query: str, max_results: int = TAVILY_SEARCH_RESULTS) -> list[dict[str, str]]:
    return run_tavily_post_research(
        topic=query,
        llm_config=None,
        user_message="",
        count=1,
        results_per_query=max_results,
    )
