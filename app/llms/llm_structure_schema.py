from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


class WritingStyle(BaseModel):
    name: str = "Custom Style"
    summary: str = ""
    tone: str = ""
    hooks: list[str] = Field(default_factory=list)
    sentence_patterns: list[str] = Field(default_factory=list)
    formatting_patterns: list[str] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    calls_to_action: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ResumeProfile(BaseModel):
    full_name: str = ""
    headline: str = ""
    location: str = ""
    skills: list[str] = Field(default_factory=list)
    experience_summary: str = ""
    achievements: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    raw_notes: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GuardrailDecision(BaseModel):
    route: Literal["modify_post", "blocked"] = "blocked"
    reason: str = ""


class GeneratedPost(BaseModel):
    post: str
    facts_used: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class PostReview(BaseModel):
    passed: bool | str = False
    feedback: str = ""
    issues: list[str] = Field(default_factory=list)
    revised_prompt_hint: str = ""

    @field_validator("passed", mode="before")
    @classmethod
    def normalize_passed(cls, value: object) -> bool:
        return _coerce_bool(value)


class ResearchFinding(BaseModel):
    title: str
    summary: str
    why_it_matters: str = ""
    suggested_post_angle: str = ""
    source_url: str = ""
    recency_signal: str = ""


class ResearchTask(BaseModel):
    title: str
    query: str
    reason: str = ""


class ResearchPlan(BaseModel):
    needs_more_user_details: bool | str = False
    tasks: list[ResearchTask] = Field(default_factory=list)

    @field_validator("needs_more_user_details", mode="before")
    @classmethod
    def normalize_needs_more_user_details(cls, value: object) -> bool:
        return _coerce_bool(value)


class ResearchResults(BaseModel):
    needs_more_user_details: bool | str = False
    query_used: str = ""
    findings: list[ResearchFinding] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    research_engine: str = ""
    status_message: str = ""

    @field_validator("needs_more_user_details", mode="before")
    @classmethod
    def normalize_needs_more_user_details(cls, value: object) -> bool:
        return _coerce_bool(value)


class ApiKeyCheck(BaseModel):
    ok: bool
    message: str
