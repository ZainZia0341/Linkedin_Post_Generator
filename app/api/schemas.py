from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiKeyTestRequest(BaseModel):
    provider: str
    model: str
    api_key: str


class ApiKeyTestResponse(BaseModel):
    ok: bool
    message: str
    provider: str
    model: str


class UserCreateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    profile: dict[str, Any] = Field(default_factory=dict)
    writing_style: dict[str, Any] | None = None


class UserUpdateRequest(BaseModel):
    profile: dict[str, Any] | None = None
    writing_style: dict[str, Any] | None = None


class UserResponse(BaseModel):
    user_id: str
    profile: dict[str, Any] = Field(default_factory=dict)
    writing_style: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class GeneratePostRequest(BaseModel):
    user_id: str
    idea: str
    generation_style: str | dict[str, Any] | None = None
    topic_source: str = "manual"
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class GenerateFromActivityRequest(BaseModel):
    user_id: str
    creator_id: str
    post_id: str
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class ModifyPostRequest(BaseModel):
    user_id: str
    thread_id: str
    modification_message: str
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class ThreadResponse(BaseModel):
    user_id: str
    thread_id: str
    current_post: str
    original_post: str = ""
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    topic: str = ""
    topic_source: str = ""
    source: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    generated_at: str = ""
    modified_at: str = ""
    modification_count: int = 0


class ThreadSummary(BaseModel):
    thread_id: str
    topic: str = ""
    topic_source: str = ""
    created_at: str
    updated_at: str


class BrainstormRequest(BaseModel):
    user_id: str
    topic: str | None = None
    action: str = "Brainstorm post topics"
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class BrainstormResponse(BaseModel):
    user_id: str
    action: str
    topic: str = ""
    ideas: list[dict[str, Any]] = Field(default_factory=list)
    research_suggestions: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class CreatorCreateRequest(BaseModel):
    user_id: str
    profile_url: str


class CreatorResponse(BaseModel):
    user_id: str
    creator_id: str
    profile_url: str
    display_name: str
    added_at: str
    updated_at: str
    last_checked_at: str | None = None
    seen_count: int = 0
    new_count: int = 0


class ScrapeCreatorsRequest(BaseModel):
    user_id: str
    creator_ids: list[str] | None = None
    max_posts: int = 5


class ActivityResponse(BaseModel):
    user_id: str
    creator_id: str
    post_id: str
    post_url: str = ""
    raw_text: str
    author_name: str = ""
    posted_at_text: str = ""
    fetched_at: str
    content_hash: str
    source: str = "playwright"
    is_new: bool = False


class ScrapeCreatorsResponse(BaseModel):
    user_id: str
    checked_creator_ids: list[str]
    new_activities: list[ActivityResponse] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class UserDataResponse(BaseModel):
    user: UserResponse
    creators: list[CreatorResponse] = Field(default_factory=list)
    threads: list[ThreadSummary] = Field(default_factory=list)
    recent_activities: list[ActivityResponse] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    ok: bool
    message: str
