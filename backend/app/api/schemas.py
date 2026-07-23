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
    post_length: str = Field(default="Medium", examples=["Short", "Medium", "Long"])
    tone: str = Field(default="Professional", examples=["Professional", "Casual"])
    writing_style: str = Field(default="Clear Builder", examples=["Clear Builder"])
    topic_source: str = Field(
        default="manual",
        description="Tracking metadata for where the idea came from, such as manual, brainstorm, or creator_activity.",
        examples=["manual"],
    )
    post_variation: str = Field(default="", description="Optional builder variation such as Actionable or Storytelling.")
    format_tags: list[str] = Field(default_factory=list, description="Optional post format instructions.")
    tone_tags: list[str] = Field(default_factory=list, description="Optional additional tone instructions.")
    angle_tags: list[str] = Field(default_factory=list, description="Optional narrative angle instructions.")
    structure: str = Field(default="", description="Optional copy structure such as AIDA, PAS, BAB, or PPP.")


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


class PostBuilderGenerateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    topic: str = Field(min_length=2, max_length=6000)
    source_url: str = ""
    post_length: str = "Medium"
    writing_style: str = "Clear Builder"
    variations: list[str] = Field(default_factory=lambda: ["Actionable"], min_length=1, max_length=3)
    formats: list[str] = Field(default_factory=list, max_length=5)
    tones: list[str] = Field(default_factory=lambda: ["Professional"], max_length=5)
    angles: list[str] = Field(default_factory=list, max_length=5)
    structure: str = ""
    post_count: int = Field(default=1, ge=1, le=3)


class PostBuilderGenerateResponse(BaseModel):
    user_id: str
    source_url: str = ""
    source_title: str = ""
    threads: list[ThreadResponse] = Field(default_factory=list)


class ContentItemCreateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    title: str = Field(min_length=1, max_length=240)
    body: str = ""
    status: str = "idea"


class ContentItemUpdateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    title: str | None = Field(default=None, max_length=240)
    body: str | None = None
    status: str | None = None
    scheduled_at: str | None = None


class ContentItemResponse(BaseModel):
    user_id: str
    content_id: str
    thread_id: str
    title: str
    body: str = ""
    status: str = "idea"
    topic_source: str = "manual"
    source: dict[str, Any] = Field(default_factory=dict)
    assets: list[str] = Field(default_factory=list)
    scheduled_at: str = ""
    created_at: str
    updated_at: str


class ContentSourceExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class ContentSourceResponse(BaseModel):
    url: str
    canonical_url: str
    title: str = ""
    description: str = ""
    text: str = ""
    word_count: int = 0
    content_type: str = ""


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


class BrainstormJobStartResponse(BaseModel):
    job_id: str
    user_id: str
    status: str
    created_at: str


class BrainstormJobStatusResponse(BaseModel):
    job_id: str
    user_id: str
    status: str
    created_at: str
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float | None = None
    error: str = ""
    result: BrainstormResponse | None = None


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
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class RecentScrapeCreatorsRequest(BaseModel):
    user_id: str
    creator_ids: list[str] | None = None
    max_posts: int = 5
    window_hours: int = Field(default=24, ge=1, le=72)
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class ScrapeCreatorProfilesRequest(BaseModel):
    user_id: str
    creator_ids: list[str] | None = None
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class ActivityResponse(BaseModel):
    user_id: str
    creator_id: str
    post_id: str
    post_url: str = ""
    raw_text: str
    author_name: str = ""
    posted_at_text: str = ""
    is_repost: bool = False
    repost_text: str = ""
    original_post_text: str = ""
    original_author_name: str = ""
    original_author_url: str = ""
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


class LinkedInPostPublishRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    thread_id: str = Field(default="", description="Optional generated thread ID that produced this post.")
    post_text: str = Field(default="", description="Final LinkedIn post text to track.")
    post_url: str = Field(default="", description="LinkedIn feed/update URL if already known.")
    post_id: str = Field(default="", description="LinkedIn post URN/activity ID if already known.")
    source: str = Field(default="platform", description="platform or direct.")


class OwnPostResponse(BaseModel):
    user_id: str
    post_id: str
    post_url: str = ""
    source: str = "platform"
    text: str = ""
    created_at_text: str = ""
    estimated_posted_at: str = ""
    first_seen_at: str = ""
    last_scraped_at: str = ""
    reaction_count: int = 0
    comment_count: int = 0
    impression_count: int = 0
    scrape_status: str = ""
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "tracked"


class LinkedInPostPublishResponse(OwnPostResponse):
    pass


class SyncRecentOwnPostsRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    profile_url: str | None = Field(
        default=None,
        description="Optional LinkedIn profile URL. If omitted, the backend tries to read it from the user profile.",
    )
    window_hours: int = Field(default=72, ge=1, le=72)
    max_posts: int = Field(default=30, ge=1, le=100)
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class SyncRecentOwnPostsResponse(BaseModel):
    user_id: str
    checked_count: int = 0
    saved_count: int = 0
    skipped_count: int = 0
    posts: list[OwnPostResponse] = Field(default_factory=list)
    skipped_posts: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class ScrapePostEngagementRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    include_likes: bool = True
    include_comments: bool = True
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class PostEngagerResponse(BaseModel):
    user_post_id: str
    user_id: str
    post_id: str
    post_url: str = ""
    profile_key: str
    profile_url: str = ""
    profile_urn: str = ""
    name: str = ""
    headline: str = ""
    connection_degree: str = ""
    engagement_types: list[str] = Field(default_factory=list)
    comment_text: str = ""
    comment_permalink: str = ""
    comment_urn: str = ""
    comment_text_hash: str = ""
    comment_timestamp_text: str = ""
    scraped_at: str = ""
    source: str = "playwright"
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class LinkedInProspectResponse(BaseModel):
    prospect_id: str
    user_id: str
    profile_key: str
    profile_url: str = ""
    profile_urn: str = ""
    name: str = ""
    headline: str = ""
    connection_degree: str = ""
    engagement_types: list[str] = Field(default_factory=list)
    engagement_count: int = 0
    source_post_ids: list[str] = Field(default_factory=list)
    source_post_count: int = 0
    latest_comment_text: str = ""
    last_engaged_at: str = ""
    latest_action_type: str = ""
    latest_action_status: str = ""
    can_reply: bool = False
    can_dm: bool = False
    can_connect: bool = False


class PostEngagementScrapeResponse(BaseModel):
    user_id: str
    post_id: str
    like_count: int = 0
    comment_count: int = 0
    engagers_saved: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
    engagers: list[PostEngagerResponse] = Field(default_factory=list)


class CommentReplyActionRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    post_id: str
    profile_urls: list[str] = Field(
        default_factory=list,
        description="Optional selected profile URLs. Empty means all stored commenters for the post.",
    )
    reply_text: str = Field(default="Thank you for sharing your thoughts.")
    dry_run: bool = Field(
        default=True,
        description="Preview mode when true. Set false to perform the selected action through Live Playwright.",
    )
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class ConnectionRequestActionRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    post_id: str
    profile_urls: list[str] = Field(
        default_factory=list,
        description="Optional selected profile URLs. Empty means all stored likers/commenters for the post.",
    )
    engagement_types: list[str] = Field(default_factory=lambda: ["like", "comment"])
    note: str = ""
    dry_run: bool = Field(default=True)
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class DmActionRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    post_id: str
    profile_urls: list[str] = Field(
        default_factory=list,
        description="Optional selected profile URLs. Empty means all stored first-degree engagers for the post.",
    )
    message: str
    dry_run: bool = Field(default=True)
    launch_delay_seconds: float = Field(default=3, ge=0, le=60)


class LinkedInActionResult(BaseModel):
    profile_url: str = ""
    profile_key: str = ""
    action_id: str = ""
    action_type: str
    status: str
    skip_reason: str = ""
    error_message: str = ""
    final_text: str = ""


class LinkedInActionBatchResponse(BaseModel):
    user_id: str
    post_id: str
    action_type: str
    results: list[LinkedInActionResult] = Field(default_factory=list)


class LinkedInActionLogResponse(BaseModel):
    action_id: str
    user_id: str
    post_id: str = ""
    profile_url: str = ""
    profile_key: str = ""
    action_type: str
    requested_text: str = ""
    final_text: str = ""
    status: str
    skip_reason: str = ""
    error_message: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


class CarouselSlide(BaseModel):
    slide_id: str
    eyebrow: str = ""
    title: str
    body: str = ""


class CarouselCreateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    title: str = Field(min_length=1, max_length=240)
    theme: str = "Signal"
    slide_count: int = Field(default=5, ge=1, le=12)


class CarouselGenerateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    topic: str = Field(min_length=2, max_length=4000)
    audience: str = "LinkedIn professionals"
    tone: str = "Professional"
    theme: str = "Signal"
    slide_count: int = Field(default=7, ge=4, le=10)


class CarouselUpdateRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    title: str | None = Field(default=None, max_length=240)
    theme: str | None = None
    slides: list[CarouselSlide] | None = Field(default=None, min_length=1, max_length=12)


class CarouselResponse(BaseModel):
    user_id: str
    carousel_id: str
    title: str
    topic: str
    audience: str = ""
    tone: str = ""
    theme: str = "Signal"
    slides: list[CarouselSlide] = Field(default_factory=list)
    status: str = "draft"
    created_at: str
    updated_at: str


class ImageGenerationRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    prompt: str = Field(min_length=3, max_length=6000)
    post_text: str = Field(default="", max_length=10000)
    aspect_ratio: str = "1:1"
    style: str = "Editorial"
    model: str = ""


class ImageAssetResponse(BaseModel):
    user_id: str
    asset_id: str
    prompt: str
    revised_prompt: str = ""
    model: str
    mime_type: str
    aspect_ratio: str
    style: str
    asset_url: str
    created_at: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class BulkCreatorImportResponse(BaseModel):
    user_id: str
    total_urls: int = 0
    added_creators: list[CreatorResponse] = Field(default_factory=list)
    skipped_existing_creator_ids: list[str] = Field(default_factory=list)
    skipped_duplicate_creator_ids: list[str] = Field(default_factory=list)
    skipped_existing_creators: list[dict[str, str]] = Field(default_factory=list)
    skipped_duplicate_creators: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class BulkCreatorPreviewResponse(BaseModel):
    user_id: str
    total_urls: int = 0
    corrected_creators: list[dict[str, str]] = Field(default_factory=list)
    new_creators: list[dict[str, str]] = Field(default_factory=list)
    existing_creators: list[dict[str, str]] = Field(default_factory=list)
    duplicate_creators: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class CreatorProfileDetailsResponse(BaseModel):
    user_id: str
    creator_id: str
    profile_url: str
    name: str = ""
    headline: str = ""
    about: str = ""
    location: str = ""
    profile_image_url: str = ""
    experience: list[str] = Field(default_factory=list)
    fetched_at: str = ""
    source: str = "playwright"


class ScrapeCreatorProfilesResponse(BaseModel):
    user_id: str
    checked_creator_ids: list[str]
    profiles: list[CreatorProfileDetailsResponse] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class ScrapeJobStartResponse(BaseModel):
    job_id: str
    job_type: str
    user_id: str
    status: str = "queued"
    status_url: str
    total_creators: int = 0
    created_at: str = ""


class ScrapeJobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    user_id: str
    status: str
    created_at: str = ""
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    total_creators: int = 0
    scraped_creators: int = 0
    total_posts: int = 0
    scraped_profiles: int = 0
    current_creator_id: str = ""
    message: str = ""
    errors: list[dict[str, str]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class ExtensionHeartbeatRequest(BaseModel):
    extension_id: str
    user_id: str = "test-user-1"
    version: str = ""


class ExtensionTaskResultRequest(BaseModel):
    extension_id: str
    user_id: str = "test-user-1"
    status: str
    data: Any = None
    error: str = ""


class ExtensionTaskLeaseRequest(BaseModel):
    extension_id: str
    user_id: str = "test-user-1"


class ExtensionTaskPollResponse(BaseModel):
    task: dict[str, Any] | None = None


class ExtensionStatusResponse(BaseModel):
    connected: bool = False
    extension_id: str = ""
    version: str = ""
    last_seen_at: str = ""
    queued_tasks: int = 0
    active_tasks: int = 0


class DashboardStatsResponse(BaseModel):
    creator_count: int = 0
    thread_count: int = 0
    activity_count: int = 0
    total_scraped_posts_count: int = 0
    new_posts_today_count: int = 0
    new_posts_from_last_scrape_count: int = 0
    needs_scraping_count: int = 0
    recently_added_count: int = 0
    recently_added_window_days: int = 7
    scraping_stale_after_hours: int = 24
    updated_at: str = ""


class UserDataResponse(BaseModel):
    user: UserResponse
    dashboard_stats: DashboardStatsResponse = Field(default_factory=DashboardStatsResponse)
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
        default="",
        description="Legacy comment angle. New clients should use style instead.",
        examples=["Add Value"],
    )
    style: str = Field(default="Add Value", description="Comment style or angle.", examples=["Add Value"])
    tone: str = Field(default="Professional", examples=["Professional", "Casual"])
    length: str = Field(default="Medium", examples=["Short", "Medium", "Long"])


class ModifyCommentRequest(BaseModel):
    user_id: str = Field(examples=["test-user-1"])
    thread_id: str
    modification_message: str = Field(examples=["Make this sound more conversational."])
    style: str | None = None
    tone: str | None = None
    length: str | None = None


class CommentResponse(BaseModel):
    user_id: str
    creator_id: str
    post_id: str
    thread_id: str = ""
    comment_topic: str
    style: str = "Add Value"
    tone: str = "Professional"
    length: str = "Medium"
    comment: str
    provider: str = ""
    model: str = ""
    generated_at: str = ""
    commented: bool = False
    modification_count: int = 0
    conversation: list[dict[str, Any]] = Field(default_factory=list)


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
