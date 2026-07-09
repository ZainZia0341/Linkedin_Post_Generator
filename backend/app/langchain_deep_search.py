from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.config import TAVILY_SEARCH_RESULTS
from app import travily_tool
from app.deep_research_agent import (
    DeepResearchReport,
    DeepResearchUnavailable,
    run_deep_research_agent,
)
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import (
    ResearchFinding,
    ResearchPlan,
    ResearchResults,
    ResearchTask,
    ResumeProfile,
)
from app.llms.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_USER_PROMPT
from app.travily_tool import search_recent_web

MAX_RESEARCH_TASKS = 4
MAX_RESEARCH_KEYWORDS = 12
RECENT_RESEARCH_TIME_RANGE = "month"

_RECENCY_QUERY_TERMS = {
    "announced",
    "announcement",
    "beta",
    "ga",
    "launch",
    "launched",
    "latest",
    "new",
    "preview",
    "recent",
    "release",
    "released",
    "roadmap",
    "trending",
}

_GENERIC_RESEARCH_KEYWORDS = {
    "architect",
    "architecture",
    "backend",
    "building",
    "cloud",
    "code",
    "coding",
    "current",
    "developer",
    "engineer",
    "engineering",
    "enterprise",
    "experience",
    "hands-on",
    "high-performance",
    "latest",
    "modern",
    "platform",
    "professional",
    "research",
    "scalable",
    "secure",
    "senior",
    "software",
    "systems",
    "technology",
    "trending",
}

_CANONICAL_TECH_PATTERNS: list[tuple[str, str]] = [
    (r"\baws\s+lambda\b|\blambda\b", "AWS Lambda"),
    (r"\bdynamodb\b|\bdynamo\s*db\b", "DynamoDB"),
    (r"\bstep\s+functions?\b", "Step Functions"),
    (r"\beventbridge\b|\bevent\s+bridge\b", "EventBridge"),
    (r"\baws\s+bedrock\b|\bbedrock\b", "AWS Bedrock"),
    (r"\bamazon\s+web\s+services\b|\baws\b", "AWS"),
    (r"\blangchain\b", "LangChain"),
    (r"\blanggraph\b", "LangGraph"),
    (r"\bai\s+agents?\b|\bagentic\s+ai\b", "AI agents"),
    (r"\bgenerative\s+ai\b|\bgenai\b", "generative AI"),
    (r"\bnode\.?js\b|\bnodejs\b", "Node.js"),
    (r"\btypescript\b", "TypeScript"),
    (r"\bjavascript\b", "JavaScript"),
    (r"\bpython\b", "Python"),
    (r"\bgraphql\b", "GraphQL"),
    (r"\brest\s+apis?\b|\brest\b", "REST APIs"),
    (r"\bmicroservices?\b", "microservices"),
    (r"\bserverless\b", "serverless"),
    (r"\bobservability\b", "observability"),
    (r"\bopentelemetry\b|\botel\b", "OpenTelemetry"),
    (r"\bterraform\b", "Terraform"),
    (r"\baws\s+cdk\b|\bcdk\b", "AWS CDK"),
    (r"\becs\b", "Amazon ECS"),
    (r"\beks\b|\bkubernetes\b|\bk8s\b", "Kubernetes"),
    (r"\bdocker\b", "Docker"),
    (r"\bstreamlit\b", "Streamlit"),
    (r"\bsql\b", "SQL"),
    (r"\bmongodb\b|\bmongo\s*db\b", "MongoDB"),
    (r"\bpayments?\b|\bfintech\b|\bmerchant\b", "payments"),
    (r"\bevent-driven\b|\bevent\s+driven\b", "event-driven architecture"),
]

RESEARCH_PLAN_SYSTEM_PROMPT = """You plan focused web research tasks for recent technology trend discovery.
Return only structured data that matches the schema."""

RESEARCH_PLAN_USER_PROMPT = """Create a concise recent-news research plan for this user's professional context.

Today's date:
{current_date}

User context:
{user_context}

Stack keywords to use as starting points:
{keywords}

Rules:
- If context is empty or too vague, set needs_more_user_details true and return no tasks.
- Otherwise create 3 to 4 focused research tasks.
- Each task should have a short title and one precise web search query.
- Avoid a single giant query copied from the entire resume.
- Search for recent launches, releases, announcements, previews, GA/beta updates, acquisitions, roadmap changes, or newly trending tools.
- Every query must include at least one recency word such as latest, recent, launch, release, announced, preview, GA, beta, roadmap, or the current year.
- Each query should combine 1 to 3 stack keywords, not the whole profile.
- Do not plan evergreen topics like general observability, idempotency, architecture tradeoffs, or cold starts unless a recent source made them newly relevant."""


def _current_date() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _current_year() -> str:
    return datetime.now(UTC).strftime("%Y")


def _profile_data(resume_profile: ResumeProfile | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(resume_profile, ResumeProfile):
        return resume_profile.model_dump()
    if isinstance(resume_profile, dict):
        return resume_profile
    return {}


def _profile_text(data: dict[str, Any], extra_details: str = "") -> str:
    raw_parts: list[str] = []
    for key in (
        "headline",
        "experience_summary",
        "raw_notes",
        "full_name",
        "location",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            raw_parts.append(value.strip())

    for key in ("skills", "industries", "achievements", "certifications", "education"):
        values = data.get(key) or []
        if isinstance(values, list):
            raw_parts.extend(str(value).strip() for value in values if str(value).strip())

    if extra_details.strip():
        raw_parts.append(extra_details.strip())

    return re.sub(r"\s+", " ", " | ".join(raw_parts)).strip()


def _clean_keyword(keyword: str) -> str:
    cleaned = re.sub(r"\s+", " ", keyword.replace("•", " ").replace("/", " / ")).strip(" -|,.;:")
    cleaned = re.sub(r"\s*/\s*", "/", cleaned)
    return cleaned


def _keyword_is_specific(keyword: str) -> bool:
    cleaned = _clean_keyword(keyword)
    if not cleaned:
        return False
    lower = cleaned.lower()
    if lower in _GENERIC_RESEARCH_KEYWORDS:
        return False
    words = re.findall(r"[A-Za-z0-9.+#-]+", cleaned)
    if len(words) > 4:
        return False
    if len(words) == 1 and lower in _GENERIC_RESEARCH_KEYWORDS:
        return False
    return True


def _add_keyword(keywords: list[str], keyword: str) -> None:
    cleaned = _clean_keyword(keyword)
    if not _keyword_is_specific(cleaned):
        return
    seen = {item.lower() for item in keywords}
    if cleaned.lower() not in seen:
        keywords.append(cleaned)


def extract_research_keywords(
    resume_profile: ResumeProfile | dict[str, Any] | None = None,
    extra_details: str = "",
    limit: int = MAX_RESEARCH_KEYWORDS,
) -> list[str]:
    """Extract concrete stack/domain keywords to seed recent trend research."""
    data = _profile_data(resume_profile)
    text = _profile_text(data, extra_details)
    keywords: list[str] = []

    for pattern, canonical in _CANONICAL_TECH_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            _add_keyword(keywords, canonical)

    for skill in data.get("skills") or []:
        for part in re.split(r"[,;|•]", str(skill)):
            _add_keyword(keywords, part)

    if len(keywords) < limit:
        token_candidates = re.findall(r"\b[A-Z][A-Za-z0-9.+#-]{1,20}\b|\b[A-Za-z]+\.js\b", text)
        for candidate in token_candidates:
            _add_keyword(keywords, candidate)
            if len(keywords) >= limit:
                break

    return keywords[:limit]


def _keyword_clusters(keywords: list[str]) -> list[str]:
    lower_keywords = {keyword.lower(): keyword for keyword in keywords}

    def present(*names: str) -> list[str]:
        found: list[str] = []
        for name in names:
            value = lower_keywords.get(name.lower())
            if value:
                found.append(value)
        return found

    clusters: list[str] = []
    cloud = present("AWS Lambda", "DynamoDB", "EventBridge", "Step Functions", "AWS Bedrock", "AWS")
    if cloud:
        clusters.append(" ".join(cloud[:4]))

    ai = present("AWS Bedrock", "LangChain", "LangGraph", "AI agents", "generative AI")
    if ai:
        clusters.append(" ".join(ai[:4]))

    backend = present("Node.js", "TypeScript", "GraphQL", "REST APIs", "microservices", "serverless")
    if backend:
        clusters.append(" ".join(backend[:4]))

    platform = present("OpenTelemetry", "observability", "Terraform", "AWS CDK", "Kubernetes", "Docker")
    if platform:
        clusters.append(" ".join(platform[:4]))

    domain = present("payments", "event-driven architecture")
    if domain:
        clusters.append(" ".join(domain[:3]))

    for keyword in keywords:
        if len(clusters) >= MAX_RESEARCH_TASKS:
            break
        if not any(keyword.lower() in cluster.lower() for cluster in clusters):
            clusters.append(keyword)

    deduped: list[str] = []
    seen: set[str] = set()
    for cluster in clusters:
        key = cluster.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cluster)
        if len(deduped) >= MAX_RESEARCH_TASKS:
            break
    return deduped


def _has_recency_intent(query: str) -> bool:
    lower_query = query.lower()
    return _current_year() in lower_query or any(term in lower_query for term in _RECENCY_QUERY_TERMS)


def _recent_query_for_cluster(cluster: str) -> str:
    return f"{cluster} latest launch release announcement preview GA beta developer news {_current_year()}"


def _profile_context(resume_profile: ResumeProfile | dict[str, Any] | None, extra_details: str = "") -> str:
    data = _profile_data(resume_profile)

    skills = ", ".join((data.get("skills") or [])[:8])
    headline = data.get("headline", "")
    industries = ", ".join((data.get("industries") or [])[:5])
    experience = data.get("experience_summary", "")
    context_parts = [headline, skills, industries, experience, extra_details]
    context = " | ".join(part for part in context_parts if part)
    return re.sub(r"\s+", " ", context).strip()


def _fallback_plan(user_context: str, keywords: list[str] | None = None) -> ResearchPlan:
    if not user_context.strip():
        return ResearchPlan(needs_more_user_details=True, tasks=[])

    keywords = keywords or extract_research_keywords(extra_details=user_context)
    clusters = _keyword_clusters(keywords)
    tasks: list[ResearchTask] = []

    for cluster in clusters:
        tasks.append(
            ResearchTask(
                title=f"Recent {cluster} updates",
                query=_recent_query_for_cluster(cluster),
                reason="The user's profile mentions this stack area, so research should check whether anything new is trending now.",
            )
        )
        if len(tasks) >= MAX_RESEARCH_TASKS:
            break

    if not tasks:
        tasks = [
            ResearchTask(
                title="Recent software engineering launches",
                query=f"latest software engineering tool launches release announcements developer news {_current_year()}",
                reason="No concrete stack keywords were found, so use broad recent software technology discovery.",
            )
        ]

    filler_tasks = [
        ResearchTask(
            title="Recent backend and cloud launches",
            query=f"latest backend cloud developer tool launches release announcements {_current_year()}",
            reason="Broad recent cloud/backend news can surface post-worthy topics if stack-specific searches are thin.",
        ),
        ResearchTask(
            title="Recent AI developer tooling launches",
            query=f"latest AI developer tooling agent framework launch release announcement {_current_year()}",
            reason="AI tooling changes quickly and may intersect with backend/cloud work.",
        ),
    ]
    for task in filler_tasks:
        if len(tasks) >= MAX_RESEARCH_TASKS:
            break
        if not any(existing.title == task.title for existing in tasks):
            tasks.append(task)

    return ResearchPlan(needs_more_user_details=False, tasks=tasks[:MAX_RESEARCH_TASKS])


def _sanitize_plan(plan: ResearchPlan, user_context: str, keywords: list[str]) -> ResearchPlan:
    if plan.needs_more_user_details:
        return plan

    sanitized_tasks: list[ResearchTask] = []
    for task in plan.tasks:
        query = re.sub(r"\s+", " ", task.query).strip()
        if not query or len(query) > 220 or not _has_recency_intent(query):
            continue
        sanitized_tasks.append(
            ResearchTask(
                title=task.title[:80] or "Recent technology update",
                query=query,
                reason=task.reason,
            )
        )
        if len(sanitized_tasks) >= MAX_RESEARCH_TASKS:
            break

    if sanitized_tasks:
        return ResearchPlan(needs_more_user_details=False, tasks=sanitized_tasks)

    return _fallback_plan(user_context, keywords)


def _plan_research(user_context: str, keywords: list[str], llm_config: LLMConfig | None) -> ResearchPlan:
    plan = invoke_structured(
        config=llm_config,
        schema=ResearchPlan,
        system_prompt=RESEARCH_PLAN_SYSTEM_PROMPT,
        user_prompt=RESEARCH_PLAN_USER_PROMPT.format(
            current_date=_current_date(),
            user_context=user_context[:2000],
            keywords=", ".join(keywords) if keywords else "No specific stack keywords found",
        ),
        fallback_factory=lambda: _fallback_plan(user_context, keywords),
    )
    if plan.needs_more_user_details or not plan.tasks:
        fallback = _fallback_plan(user_context, keywords)
        if fallback.tasks:
            return fallback
    return _sanitize_plan(plan, user_context, keywords)


def _research_task(task: ResearchTask, max_results: int) -> list[dict[str, str]]:
    print(f"Deep research task: {task.title} -> {task.query}")
    results = search_recent_web(
        task.query,
        max_results=max_results,
        time_range=RECENT_RESEARCH_TIME_RANGE,
    )
    normalized = []
    for result in results:
        normalized.append(
            {
                "task": task.title,
                "query": result.get("query", task.query),
                "title": result.get("title", ""),
                "content": result.get("content", ""),
                "url": result.get("url", ""),
                "published_date": result.get("published_date", ""),
            }
        )
    return normalized


def _format_search_results(search_results: list[dict[str, str]]) -> str:
    lines = []
    for index, result in enumerate(search_results, start=1):
        lines.append(
            "\n".join(
                [
                    f"[{index}] Task: {result.get('task', '')}",
                    f"Title: {result.get('title', '')}",
                    f"Published: {result.get('published_date', '')}",
                    f"Summary: {result.get('content', '')}",
                    f"URL: {result.get('url', '')}",
                ]
            )
        )
    return "\n\n".join(lines)


def _source_urls_from_text(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)\]]+", text)
    cleaned_urls = [url.rstrip(".,;") for url in urls]
    return list(dict.fromkeys(cleaned_urls))


def _fallback_results_from_deep_report(
    report: DeepResearchReport,
) -> ResearchResults:
    source_urls = _source_urls_from_text(report.report)
    sections = [
        section.strip()
        for section in re.split(r"\n#{2,3}\s+", report.report)
        if section.strip() and "sources" not in section.lower()[:20]
    ]
    findings: list[ResearchFinding] = []
    for index, section in enumerate(sections[:5]):
        lines = [line.strip("# ").strip() for line in section.splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0][:120]
        summary = " ".join(lines[1:])[:600] or lines[0][:600]
        findings.append(
            ResearchFinding(
                title=title,
                summary=summary,
                why_it_matters="This topic is backed by the Deep Agents research report.",
                suggested_post_angle=f"Use '{title}' only if the cited source shows a timely change worth reacting to.",
                source_url=source_urls[index] if index < len(source_urls) else "",
                recency_signal="Extracted from the recent technology trend discovery report.",
            )
        )

    if not findings:
        findings.append(
            ResearchFinding(
                title="Deep research report",
                summary=report.report[:800],
                why_it_matters="The official Deep Agents workflow produced this source-backed research summary.",
                suggested_post_angle="Use the strongest cited finding as the core LinkedIn post angle.",
                source_url=source_urls[0] if source_urls else "",
                recency_signal="Review the cited report for the newest launch, release, or announcement signal.",
            )
        )

    return ResearchResults(
        needs_more_user_details=False,
        query_used=report.request,
        findings=findings,
        provider=report.provider,
        model=report.model,
        research_engine="deepagents",
        status_message="Official Deep Agents research completed.",
    )


def _synthesize_deep_report(
    report: DeepResearchReport,
    user_context: str,
    llm_config: LLMConfig | None,
) -> ResearchResults:
    result = invoke_structured(
        config=llm_config,
        schema=ResearchResults,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_prompt=RESEARCH_USER_PROMPT.format(
            user_context=user_context[:2000],
            search_results=(
                "Official Deep Agents research report:\n\n"
                f"{report.report[:12000]}"
            ),
        ),
        fallback_factory=lambda: _fallback_results_from_deep_report(report),
    )
    result.provider = report.provider
    result.model = report.model
    result.query_used = result.query_used or report.request
    result.research_engine = "deepagents"
    result.status_message = result.status_message or "Official Deep Agents research completed."
    return result


def _build_deep_research_request(user_context: str, keywords: list[str]) -> str:
    return (
        "Discover recent technology news, launches, releases, announcements, previews, "
        "GA/beta updates, roadmap changes, and newly trending tools that could become "
        "LinkedIn post topics for this professional profile. "
        "Use the stack keywords as starting points, then decide which recent items are "
        "actually post-worthy. Do not return evergreen architecture advice unless a "
        "recent source shows why it is newly relevant now.\n\n"
        f"Today's date: {_current_date()}\n"
        f"Stack keywords: {', '.join(keywords) if keywords else 'No concrete stack keywords found'}\n\n"
        f"Professional context:\n{user_context}"
    )


def _fallback_research_results(
    query: str,
    provider: str,
    model: str,
    search_results: list[dict[str, str]] | None = None,
    needs_more_details: bool = False,
    status_message: str = "",
) -> ResearchResults:
    if needs_more_details:
        return ResearchResults(
            needs_more_user_details=True,
            query_used=query,
            findings=[],
            provider=provider,
            model=model,
            research_engine="fallback",
            status_message=status_message or "More profile details are needed before research can run.",
        )

    search_results = search_results or []
    grouped_results: dict[str, list[dict[str, str]]] = {}
    for result in search_results:
        task_name = result.get("task") or result.get("query") or "Research topic"
        grouped_results.setdefault(task_name, []).append(result)

    findings: list[ResearchFinding] = []
    for task_name, task_results in list(grouped_results.items())[:5]:
        source = _best_source_result(task_results)
        title = task_name[:120]
        summary = _summarize_task_results(task_name, task_results)
        findings.append(
            ResearchFinding(
                title=title,
                summary=summary,
                why_it_matters="This connects current research to the user's professional context.",
                suggested_post_angle=f"Use this as a post only if the source shows a new launch, release, announcement, or trend signal about {task_name}.",
                source_url=source.get("url", ""),
                recency_signal=_recency_signal(task_results),
            )
        )

    if not findings:
        findings = [
            ResearchFinding(
                title="Current professional trend discovery",
                summary="Add more profile details or a narrower domain to improve research quality.",
                why_it_matters="The research agent needs context to avoid generic topic ideas.",
                suggested_post_angle="Share one specific recent problem, tradeoff, or lesson from your work.",
                source_url="",
                recency_signal="No recent source signal was found.",
            )
        ]

    return ResearchResults(
        needs_more_user_details=False,
        query_used=query,
        findings=findings,
        provider=provider,
        model=model,
        research_engine="fallback",
        status_message=status_message or "Used fallback focused Tavily research.",
    )


def _recency_signal(results: list[dict[str, str]]) -> str:
    published_dates = [
        result.get("published_date", "").strip()
        for result in results
        if result.get("published_date", "").strip()
    ]
    if published_dates:
        return f"Recent search result date(s): {', '.join(published_dates[:3])}."
    return "Collected through recent Tavily news search; verify source dates before publishing."


def _best_source_result(results: list[dict[str, str]]) -> dict[str, str]:
    for result in results:
        if result.get("url"):
            return result
    return results[0] if results else {}


def _clean_result_text(text: str, max_chars: int = 380) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"(?i)^tavily answer\s*", "", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    sentence_cut = cleaned[:max_chars].rsplit(". ", 1)[0]
    if len(sentence_cut) >= 120:
        return sentence_cut.rstrip(".") + "."
    return cleaned[:max_chars].rstrip() + "..."


def _summarize_task_results(task_name: str, results: list[dict[str, str]]) -> str:
    useful_results = [result for result in results if result.get("content")]
    if not useful_results:
        return f"Use this research task as a starting point for a current LinkedIn angle about {task_name}."

    snippets = []
    for result in useful_results[:3]:
        title = result.get("title", "").strip()
        if title.lower() == "tavily answer":
            title = ""
        text = _clean_result_text(result.get("content", ""))
        if not text:
            continue
        snippets.append(f"{title}: {text}" if title else text)

    if not snippets:
        return f"Use this research task as a starting point for a current LinkedIn angle about {task_name}."
    return " ".join(snippets)[:650]


def research_trending_topics(
    resume_profile: ResumeProfile | dict[str, Any] | None = None,
    llm_config: LLMConfig | None = None,
    extra_details: str = "",
    max_results: int = TAVILY_SEARCH_RESULTS,
) -> ResearchResults:
    provider = llm_config.provider if llm_config else ""
    model = llm_config.model if llm_config else ""
    user_context = _profile_context(resume_profile, extra_details)
    keywords = extract_research_keywords(resume_profile, extra_details)
    if not user_context:
        print("Deep research needs user details before searching.")
        return _fallback_research_results(
            query="",
            provider=provider,
            model=model,
            needs_more_details=True,
        )

    fallback_status = ""
    if llm_config is not None and llm_config.resolved_api_key() and travily_tool.get_tavily_api_key():
        try:
            deep_report = run_deep_research_agent(
                request=_build_deep_research_request(user_context, keywords),
                llm_config=llm_config,
            )
            return _synthesize_deep_report(deep_report, user_context, llm_config)
        except DeepResearchUnavailable as exc:
            fallback_status = f"Official Deep Agents unavailable; used fallback focused research. Reason: {exc}"
            print(fallback_status)
        except Exception as exc:
            fallback_status = f"Official Deep Agents failed unexpectedly; used fallback focused research. Reason: {exc}"
            print(fallback_status)

    plan = _plan_research(user_context, keywords, llm_config)
    if plan.needs_more_user_details or not plan.tasks:
        print("Deep research plan needs more user details.")
        return _fallback_research_results(
            query=user_context,
            provider=provider,
            model=model,
            needs_more_details=True,
            status_message=fallback_status,
        )

    all_search_results: list[dict[str, str]] = []
    for task in plan.tasks:
        all_search_results.extend(_research_task(task, max_results=max(2, max_results // 2)))

    query_used = " | ".join(task.query for task in plan.tasks)
    result = invoke_structured(
        config=llm_config,
        schema=ResearchResults,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_prompt=RESEARCH_USER_PROMPT.format(
            user_context=user_context[:2000],
            search_results=_format_search_results(all_search_results)[:12000],
        ),
        fallback_factory=lambda: _fallback_research_results(
            query_used,
            provider,
            model,
            all_search_results,
            status_message=fallback_status,
        ),
    )
    result.provider = provider
    result.model = model
    result.query_used = result.query_used or query_used
    result.research_engine = result.research_engine or ("fallback" if fallback_status else "focused")
    result.status_message = result.status_message or fallback_status or "Used focused Tavily research."
    return result
