from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from deepagents import create_deep_agent
from langchain.tools import InjectedToolArg, tool
from langchain_core.messages import HumanMessage
from markdownify import markdownify
from tavily import TavilyClient

from app import travily_tool
from app.llms.llm import LLMConfig, create_chat_model

MAX_FETCH_CHARS = 9000
DEFAULT_HTTP_TIMEOUT = 10.0
MAX_CONCURRENT_RESEARCH_UNITS = 3
MAX_RESEARCHER_ITERATIONS = 3


class DeepResearchUnavailable(RuntimeError):
    """Raised when deep research cannot run because runtime requirements are missing."""


@dataclass(slots=True)
class DeepResearchReport:
    request: str
    report: str
    provider: str
    model: str


def fetch_webpage_content(url: str, timeout: float = DEFAULT_HTTP_TIMEOUT) -> str:
    """Fetch a webpage and convert it to compact Markdown text."""
    if not url.strip():
        return "Error fetching webpage: empty URL."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        )
    }
    try:
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        markdown = markdownify(response.text)
        markdown = "\n".join(line.rstrip() for line in markdown.splitlines())
        markdown = "\n".join(line for line in markdown.splitlines() if line.strip())
        return markdown[:MAX_FETCH_CHARS]
    except httpx.HTTPError as exc:
        return f"Error fetching {url}: {exc}"
    except Exception as exc:
        return f"Unexpected error fetching {url}: {exc}"


@tool(parse_docstring=True)
def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 3,
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "news",
    time_range: Annotated[Literal["day", "week", "month", "year"], InjectedToolArg] = "month",
) -> str:
    """Search recent web/news results and return full webpage content for discovered sources.

    Args:
        query: Search query to execute.
        max_results: Maximum number of search results to return.
        topic: Tavily topic filter. News is the default for trend discovery.
        time_range: Tavily recency filter. Month is the default for recent launches.

    Returns:
        Formatted search results with source titles, URLs, and fetched page content.
    """
    api_key = travily_tool.get_tavily_api_key()
    if not api_key:
        return "Tavily API key is missing. Cannot run live web search."

    try:
        client = TavilyClient(api_key=api_key)
        search_results = client.search(
            query=query,
            max_results=max_results,
            topic=topic,
            time_range=time_range,
            search_depth="advanced",
            include_answer=True,
        )
    except Exception as exc:
        return f"Tavily search failed for '{query}': {exc}"

    result_texts: list[str] = []
    answer = search_results.get("answer")
    if answer:
        result_texts.append(f"## Tavily Answer\n\n{answer}\n---")

    for result in search_results.get("results", []) or []:
        url = str(result.get("url", ""))
        title = str(result.get("title", "Untitled source"))
        snippet = str(result.get("content", ""))
        content = fetch_webpage_content(url) if url else "No URL returned for this result."
        result_texts.append(
            f"## {title}\n"
            f"**URL:** {url}\n\n"
            f"**Search snippet:** {snippet}\n\n"
            f"{content}\n---"
        )

    if not result_texts:
        return f"No Tavily results found for '{query}'."

    return f"Found {len(result_texts)} result(s) for '{query}':\n\n" + "\n".join(result_texts)


RESEARCH_WORKFLOW_INSTRUCTIONS = """# Recent Technology Trend Discovery Workflow

Follow this workflow for all research requests:

1. Plan: create a todo list that breaks the request into focused recent-news research tasks.
2. Save the request: write the original request to `/research_request.md`.
3. Research: delegate focused research tasks to the research sub-agent. Use the
   sub-agent for web research rather than doing all research in the orchestrator.
4. Assess: after findings return, identify gaps and run another focused search
   only if the answer is still weak.
5. Synthesize: consolidate findings into a concise professional research report.
6. Verify: confirm the final report addresses the original request and cites sources.

Report writing guidelines:
- Focus on recently launched, announced, released, previewed, or newly trending
  technology topics relevant to the user's stack.
- Treat evergreen architecture advice as background only. Do not return it as a
  candidate topic unless a recent source explains why it is newly relevant now.
- Prefer specific launch/release/news items over broad generic trend lists.
- Include what is new, why it matters now, and whether the topic looks post-worthy.
- Do not invent source URLs, numbers, tools, or claims.
- Cite sources inline with [1], [2], [3].
- End with a `### Sources` section listing each numbered source and URL.
- Keep the report concise enough to use inside a Streamlit UI.
"""

RESEARCHER_INSTRUCTIONS = """You are a research assistant. Today's date is {date}.

Use the tavily_search tool to gather current information for the delegated task.

Research rules:
- Start with one focused query that includes terms such as latest, launch,
  release, announced, preview, GA, beta, roadmap, or the current year.
- Use 2 to 3 search calls for ordinary topics.
- Use up to 5 search calls only when the topic is complex or sources disagree.
- Stop when you have enough relevant, current, source-backed findings.
- Prefer primary or high-quality sources when available.
- Prefer sources from the last 30 to 90 days. Older sources are useful only as
  context, not as the main trend signal.
- Skip generic evergreen explanations unless they support a newer launch or news item.
- Include source URLs and inline citations in your findings.
"""

SUBAGENT_DELEGATION_INSTRUCTIONS = """# Sub-Agent Research Coordination

Use at most {max_concurrent_research_units} parallel research tasks per round.
Stop after {max_researcher_iterations} delegation rounds.

Use one comprehensive sub-agent for simple topics. Use multiple sub-agents only
when the request has clearly distinct aspects, such as cloud architecture,
payments engineering, AI systems, or career-positioning angles.
"""


def _extract_report_text(result: object) -> str:
    if not isinstance(result, dict):
        return str(result)

    messages = result.get("messages", [])
    text_parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            text_parts.append(content.strip())

    if text_parts:
        return text_parts[-1]

    for key in ("final_report", "report", "output"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return str(result)


def build_deep_research_agent(llm_config: LLMConfig):
    if not llm_config.resolved_api_key():
        raise DeepResearchUnavailable("LLM API key is missing.")
    if not travily_tool.get_tavily_api_key():
        raise DeepResearchUnavailable("Tavily API key is missing.")

    model = create_chat_model(llm_config)
    current_date = datetime.now(UTC).strftime("%Y-%m-%d")
    instructions = (
        RESEARCH_WORKFLOW_INSTRUCTIONS
        + "\n\n"
        + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
            max_concurrent_research_units=MAX_CONCURRENT_RESEARCH_UNITS,
            max_researcher_iterations=MAX_RESEARCHER_ITERATIONS,
        )
    )
    research_sub_agent = {
        "name": "research-agent",
        "description": "Conduct focused source-backed web research for one delegated topic.",
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": [tavily_search],
        "model": model,
    }

    return create_deep_agent(
        model=model,
        tools=[tavily_search],
        system_prompt=instructions,
        subagents=[research_sub_agent],
    )


def run_deep_research_agent(request: str, llm_config: LLMConfig) -> DeepResearchReport:
    if not request.strip():
        raise DeepResearchUnavailable("Research request is empty.")

    agent = build_deep_research_agent(llm_config)
    print("Starting official Deep Agents research workflow.")
    try:
        result = agent.invoke({"messages": [HumanMessage(content=request)]})
    except Exception as exc:
        raise DeepResearchUnavailable(f"Deep Agents research failed: {exc}") from exc

    report = _extract_report_text(result)
    if not report.strip():
        raise DeepResearchUnavailable("Deep Agents returned an empty report.")

    print("Deep Agents research workflow completed.")
    return DeepResearchReport(
        request=request,
        report=report,
        provider=llm_config.provider,
        model=llm_config.model,
    )
