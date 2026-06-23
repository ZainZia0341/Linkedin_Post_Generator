from __future__ import annotations

from typing import Any

from app.config import TAVILY_SEARCH_RESULTS
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import ResearchFinding, ResearchResults, ResumeProfile
from app.llms.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_USER_PROMPT
from app.travily_tool import search_web


def _profile_context(resume_profile: ResumeProfile | dict[str, Any] | None, extra_details: str = "") -> str:
    if isinstance(resume_profile, ResumeProfile):
        data = resume_profile.model_dump()
    elif isinstance(resume_profile, dict):
        data = resume_profile
    else:
        data = {}

    skills = ", ".join(data.get("skills", []) or [])
    headline = data.get("headline", "")
    industries = ", ".join(data.get("industries", []) or [])
    context_parts = [headline, skills, industries, extra_details]
    return " | ".join(part for part in context_parts if part)


def _fallback_research_results(
    query: str,
    provider: str,
    model: str,
    needs_more_details: bool = False,
) -> ResearchResults:
    if needs_more_details:
        return ResearchResults(
            needs_more_user_details=True,
            query_used=query,
            findings=[],
            provider=provider,
            model=model,
        )

    topics = [
        "AI-assisted workflows",
        "practical personal branding",
        "trust and verification in generated content",
        "career storytelling with evidence",
        "automation for repeatable work",
    ]
    findings = [
        ResearchFinding(
            title=topic,
            summary=f"Explore how {topic.lower()} connects to the user's background.",
            why_it_matters="It gives the post a timely angle while staying grounded in the user's experience.",
            suggested_post_angle=f"Share one practical lesson about {topic.lower()} and a specific action readers can try.",
            source_url="",
        )
        for topic in topics
    ]
    return ResearchResults(
        needs_more_user_details=False,
        query_used=query,
        findings=findings,
        provider=provider,
        model=model,
    )


def research_trending_topics(
    resume_profile: ResumeProfile | dict[str, Any] | None = None,
    llm_config: LLMConfig | None = None,
    extra_details: str = "",
    max_results: int = TAVILY_SEARCH_RESULTS,
) -> ResearchResults:
    provider = llm_config.provider if llm_config else ""
    model = llm_config.model if llm_config else ""
    user_context = _profile_context(resume_profile, extra_details)
    if not user_context:
        print("Deep research needs user details before searching.")
        return _fallback_research_results(
            query="",
            provider=provider,
            model=model,
            needs_more_details=True,
        )

    query = f"trending professional topics for {user_context}"
    search_results = search_web(query, max_results)
    search_text = "\n".join(
        f"- {result.get('title', '')}: {result.get('content', '')} {result.get('url', '')}"
        for result in search_results
    )
    return invoke_structured(
        config=llm_config,
        schema=ResearchResults,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_prompt=RESEARCH_USER_PROMPT.format(
            user_context=user_context,
            search_results=search_text,
        ),
        fallback_factory=lambda: _fallback_research_results(query, provider, model),
    )
