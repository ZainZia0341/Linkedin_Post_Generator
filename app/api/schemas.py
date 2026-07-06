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
    user_id: str = Field(examples=["test-user-1"])
    idea: str = Field(
        description="The topic or instruction to create the LinkedIn post about.",
        examples=["Create a post on Claude Fable 5 return"],
    )
    generation_style: str = Field(
        default="Create a post about a topic",
        description=(
            "Post creation template to use. Examples: Create posts from scratch, "
            "Create a controversial post about a topic, Create a top mistakes post about a topic."
        ),
        examples=["Create a post about a topic"],
    )
    topic_source: str = Field(
        default="manual",
        description="Tracking metadata for where the idea came from, such as manual, brainstorm, or creator_activity.",
        examples=["manual"],
    )


class GenerateFromActivityRequest(BaseModel):
    user_id: str
    creator_id: str
    post_id: str


class ModifyPostRequest(BaseModel):
    user_id: str
    thread_id: str
    modification_message: str


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
    generation_style: str = ""
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
    generation_style: str = ""
    created_at: str
    updated_at: str


class BrainstormRequest(BaseModel):
    user_id: str
    topic: str | None = None
    action: str = "Brainstorm post topics"


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


class RecentScrapeCreatorsRequest(BaseModel):
    user_id: str
    creator_ids: list[str] | None = None
    max_posts: int = 5
    window_hours: int = Field(default=24, ge=1, le=168)


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
    engagement: dict[str, Any] = Field(default_factory=dict)


class ScrapeCreatorsResponse(BaseModel):
    user_id: str
    checked_creator_ids: list[str]
    new_activities: list[ActivityResponse] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class RecentScrapeCreatorsResponse(BaseModel):
    user_id: str
    checked_creator_ids: list[str]
    window_hours: int = 24
    activities: list[ActivityResponse] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class RecentActivitiesResponse(BaseModel):
    user_id: str
    window_hours: int = 24
    activities: list[ActivityResponse] = Field(default_factory=list)


class BulkCreatorImportResponse(BaseModel):
    user_id: str
    total_urls: int = 0
    added_creators: list[CreatorResponse] = Field(default_factory=list)
    skipped_existing_creator_ids: list[str] = Field(default_factory=list)
    skipped_duplicate_creator_ids: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class UserDataResponse(BaseModel):
    user: UserResponse
    creators: list[CreatorResponse] = Field(default_factory=list)
    threads: list[ThreadSummary] = Field(default_factory=list)
    recent_activities: list[ActivityResponse] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    ok: bool
    message: str


class GenerateCommentRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    creator_id: str = Field(examples=["shubhamsaboo"])
    post_id: str = Field(examples=["urn:li:activity:7478273041442033664"])
    comment_topic: str = Field(
        default="Add Value",
        description="Comment angle to generate.",
        examples=["Add Value"],
    )


class CommentResponse(BaseModel):
    user_id: str
    creator_id: str
    post_id: str
    comment_topic: str
    comment: str
    provider: str = ""
    model: str = ""
    generated_at: str = ""
    commented: bool = False


class MarkCommentedRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    creator_id: str = Field(examples=["shubhamsaboo"])
    post_id: str = Field(examples=["urn:li:activity:7478273041442033664"])
    commented: bool = Field(default=True, description="Whether this saved creator post has been commented on.")
    comment_text: str | None = Field(default=None, description="Optional final comment text that was actually posted.")


class CommentedActivityResponse(ActivityResponse):
    comment_topic: str = ""
    comment: str = ""
    commented_at: str = ""
