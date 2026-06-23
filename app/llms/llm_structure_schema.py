from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    passed: bool = False
    feedback: str = ""
    issues: list[str] = Field(default_factory=list)
    revised_prompt_hint: str = ""


class ResearchFinding(BaseModel):
    title: str
    summary: str
    why_it_matters: str = ""
    suggested_post_angle: str = ""
    source_url: str = ""


class ResearchResults(BaseModel):
    needs_more_user_details: bool = False
    query_used: str = ""
    findings: list[ResearchFinding] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class ApiKeyCheck(BaseModel):
    ok: bool
    message: str
