from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas import (
    ActivityResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    BrainstormRequest,
    BrainstormResponse,
    BrainstormJobStartResponse,
    BrainstormJobStatusResponse,
    BulkCreatorImportResponse,
    BulkCreatorPreviewResponse,
    CommentReplyActionRequest,
    CommentResponse,
    CommentedActivityResponse,
    CarouselCreateRequest,
    CarouselGenerateRequest,
    CarouselResponse,
    CarouselUpdateRequest,
    ConnectionRequestActionRequest,
    ContentItemCreateRequest,
    ContentItemResponse,
    ContentItemUpdateRequest,
    ContentSourceExtractRequest,
    ContentSourceResponse,
    CreatorCreateRequest,
    CreatorProfileDetailsResponse,
    CreatorResponse,
    DeleteResponse,
    DmActionRequest,
    ExtensionHeartbeatRequest,
    ExtensionStatusResponse,
    ExtensionTaskLeaseRequest,
    ExtensionTaskPollResponse,
    ExtensionTaskResultRequest,
    GenerateCommentRequest,
    GenerateFromActivityRequest,
    GeneratePostRequest,
    LinkedInActionBatchResponse,
    LinkedInActionLogResponse,
    LinkedInProspectResponse,
    LinkedInPostPublishRequest,
    LinkedInPostPublishResponse,
    MarkCommentedRequest,
    ModifyCommentRequest,
    ModifyPostRequest,
    ImageAssetResponse,
    ImageGenerationRequest,
    OwnPostResponse,
    PostEngagementScrapeResponse,
    PostEngagerResponse,
    PostBuilderGenerateRequest,
    PostBuilderGenerateResponse,
    RecentActivitiesResponse,
    RecentScrapeCreatorsRequest,
    RecentScrapeCreatorsResponse,
    ScrapeCreatorProfilesRequest,
    ScrapeCreatorProfilesResponse,
    ScrapeJobStartResponse,
    ScrapeJobStatusResponse,
    ScrapePostEngagementRequest,
    ScrapeCreatorsRequest,
    ScrapeCreatorsResponse,
    SyncRecentOwnPostsRequest,
    SyncRecentOwnPostsResponse,
    ThreadResponse,
    ThreadSummary,
    UserCreateRequest,
    UserDataResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.api.services import (
    COMMENT_TOPICS,
    POST_CREATION_ACTIONS,
    SAVED_ACTIONS,
    brainstorm,
    build_dashboard_stats,
    create_creator,
    create_user,
    delete_creator_with_activities,
    generate_comment,
    generate_from_activity,
    generate_post,
    get_creator_profile_details,
    import_creators_from_file,
    list_commented_activities,
    list_all_activities,
    list_linkedin_action_logs,
    list_linkedin_prospects,
    list_linkedin_post_engagers,
    list_linkedin_posts,
    list_creator_profile_details,
    list_recent_activities_from_db,
    mark_activity_commented,
    modify_comment,
    modify_post,
    preview_creators_from_file,
    process_extension_scrape_task,
    scrape_creator_profile_details,
    scrape_creators_recent_24h,
    scrape_linkedin_post_engagement_service,
    seed_default_users,
    send_comment_replies,
    send_connection_requests,
    send_dms,
    get_scrape_job,
    start_profile_scrape_job,
    start_recent_scrape_job,
    sync_recent_linkedin_posts,
    thread_response,
    thread_summary,
    track_published_linkedin_post,
    update_user,
    user_response,
)
from app.content_workflows import (
    create_carousel,
    create_content_item,
    delete_image_asset,
    extract_content_source,
    generate_carousel,
    generate_image_asset,
    generate_post_builder_variations,
    get_image_asset_path,
    list_carousels,
    list_content_items,
    list_image_assets,
    update_carousel,
    update_content_item,
)
from app.config import API_LIST_LIMIT, EXTENSION_API_TOKEN, PROVIDER_MODELS, SCRAPING_ENABLED
from app.db.dynamodb import DynamoRepository, DynamoUnavailable, get_repository
from app.extension_scraping import (
    claim_extension_task,
    complete_extension_task,
    extension_status,
    heartbeat_extension,
    renew_extension_task_lease,
)
from app.brainstorm_jobs import get_brainstorm_job, start_brainstorm_job
from app.llms.llm import LLMConfig, test_provider_api_key

app = FastAPI(
    title="LinkedIn Post Generator API",
    description="FastAPI backend for post generation, creator tracking, and DynamoDB Local persistence.",
    version="0.2.0",
)

_db_ready = False


def repo_dependency() -> DynamoRepository:
    global _db_ready
    repo = get_repository()
    if not _db_ready:
        try:
            repo.ensure_tables()
            seed_default_users(repo)
            _db_ready = True
        except DynamoUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return repo


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


def _require_scraping_enabled() -> None:
    if SCRAPING_ENABLED:
        return
    raise HTTPException(
        status_code=501,
        detail=(
            "Scraping is disabled in this deployment. Run the Chrome extension scraping workflow locally "
            "and save results to the configured DynamoDB tables."
        ),
    )


def _require_extension_token(token: str) -> None:
    if not EXTENSION_API_TOKEN or token == EXTENSION_API_TOKEN:
        return
    raise HTTPException(status_code=401, detail="Invalid Chrome extension API token.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extension/heartbeat", response_model=ExtensionStatusResponse)
def extension_heartbeat_endpoint(
    payload: ExtensionHeartbeatRequest,
    x_extension_token: Annotated[str, Header()] = "",
) -> ExtensionStatusResponse:
    _require_extension_token(x_extension_token)
    heartbeat_extension(payload.user_id, payload.extension_id, payload.version)
    return ExtensionStatusResponse.model_validate(extension_status(payload.user_id))


@app.get("/extension/tasks/next", response_model=ExtensionTaskPollResponse)
def claim_extension_task_endpoint(
    extension_id: str,
    user_id: str = "test-user-1",
    version: str = "",
    x_extension_token: Annotated[str, Header()] = "",
) -> ExtensionTaskPollResponse:
    _require_extension_token(x_extension_token)
    task = claim_extension_task(user_id, extension_id, version)
    return ExtensionTaskPollResponse(task=task)


@app.post("/extension/tasks/{task_id}/result", response_model=ExtensionStatusResponse)
def complete_extension_task_endpoint(
    task_id: str,
    payload: ExtensionTaskResultRequest,
    x_extension_token: Annotated[str, Header()] = "",
) -> ExtensionStatusResponse:
    _require_extension_token(x_extension_token)
    try:
        task = complete_extension_task(
            task_id,
            payload.user_id,
            payload.extension_id,
            payload.status,
            payload.data,
            payload.error,
        )
        process_extension_scrape_task(get_repository(), task)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExtensionStatusResponse.model_validate(extension_status(payload.user_id))


@app.post("/extension/tasks/{task_id}/lease", response_model=ExtensionStatusResponse)
def renew_extension_task_lease_endpoint(
    task_id: str,
    payload: ExtensionTaskLeaseRequest,
    x_extension_token: Annotated[str, Header()] = "",
) -> ExtensionStatusResponse:
    _require_extension_token(x_extension_token)
    try:
        renew_extension_task_lease(task_id, payload.user_id, payload.extension_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExtensionStatusResponse.model_validate(extension_status(payload.user_id))


@app.get("/extension/status", response_model=ExtensionStatusResponse)
def extension_status_endpoint(
    user_id: str = "test-user-1",
    x_extension_token: Annotated[str, Header()] = "",
) -> ExtensionStatusResponse:
    _require_extension_token(x_extension_token)
    return ExtensionStatusResponse.model_validate(extension_status(user_id))


@app.get("/actions", response_model=list[str])
def list_saved_actions() -> list[str]:
    return SAVED_ACTIONS


@app.get("/post-generation-styles", response_model=list[str])
def list_post_generation_styles() -> list[str]:
    return POST_CREATION_ACTIONS


@app.get("/comments/topics", response_model=list[str])
def list_comment_topics() -> list[str]:
    return COMMENT_TOPICS


@app.get("/llms/providers")
def list_llm_providers() -> dict[str, list[str]]:
    return PROVIDER_MODELS


@app.post("/llms/test-key", response_model=ApiKeyTestResponse)
def test_api_key(payload: ApiKeyTestRequest) -> ApiKeyTestResponse:
    result = test_provider_api_key(
        LLMConfig(provider=payload.provider, model=payload.model, api_key=payload.api_key)
    )
    return ApiKeyTestResponse(
        ok=result.ok,
        message=result.message,
        provider=payload.provider,
        model=payload.model,
    )


@app.post("/users", response_model=UserResponse)
def add_user(payload: UserCreateRequest, repo: Annotated[DynamoRepository, Depends(repo_dependency)]) -> UserResponse:
    return create_user(repo, payload.user_id, payload.profile, payload.writing_style)


@app.get("/users", response_model=list[UserResponse])
def list_users(
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> list[UserResponse]:
    return [user_response(user) for user in repo.list_users(limit)]


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, repo: Annotated[DynamoRepository, Depends(repo_dependency)]) -> UserResponse:
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return user_response(user)


@app.patch("/users/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: str,
    payload: UserUpdateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> UserResponse:
    try:
        return update_user(repo, user_id, payload.profile, payload.writing_style)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/data", response_model=UserDataResponse)
def get_user_data(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=1000),
) -> UserDataResponse:
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    creator_records = repo.list_creators(user_id, limit)
    thread_records = repo.list_threads(user_id, limit)
    creators = [CreatorResponse.model_validate(creator) for creator in creator_records]
    threads = [thread_summary(thread) for thread in thread_records]
    activities = list_all_activities(repo, user_id, limit)
    dashboard_stats = build_dashboard_stats(
        creator_records,
        thread_records,
        activities,
        existing_stats=dict(user.get("dashboard_stats") or {}),
    )
    repo.put_user({**user, "dashboard_stats": dashboard_stats.model_dump()})
    return UserDataResponse(
        user=user_response(user),
        dashboard_stats=dashboard_stats,
        creators=creators,
        threads=threads,
        recent_activities=activities,
    )


@app.post("/posts/generate", response_model=ThreadResponse)
def generate_post_endpoint(
    payload: GeneratePostRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    try:
        return generate_post(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/posts/builder/generate", response_model=PostBuilderGenerateResponse)
def generate_post_builder_endpoint(
    payload: PostBuilderGenerateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> PostBuilderGenerateResponse:
    try:
        return generate_post_builder_variations(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/posts/modify", response_model=ThreadResponse)
def modify_post_endpoint(
    payload: ModifyPostRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    try:
        return modify_post(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/posts/from-creator-activity", response_model=ThreadResponse)
def generate_from_creator_activity_endpoint(
    payload: GenerateFromActivityRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    try:
        return generate_from_activity(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/comments/generate", response_model=CommentResponse)
def generate_comment_endpoint(
    payload: GenerateCommentRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CommentResponse:
    try:
        return generate_comment(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/comments/modify", response_model=CommentResponse)
def modify_comment_endpoint(
    payload: ModifyCommentRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CommentResponse:
    try:
        return modify_comment(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.patch("/comments/mark", response_model=CommentResponse)
def mark_comment_endpoint(
    payload: MarkCommentedRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CommentResponse:
    try:
        return mark_activity_commented(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/ideas/brainstorm", response_model=BrainstormJobStartResponse, status_code=202)
def brainstorm_endpoint(
    payload: BrainstormRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> BrainstormJobStartResponse:
    try:
        return start_brainstorm_job(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/ideas/brainstorm/jobs/{job_id}", response_model=BrainstormJobStatusResponse)
def brainstorm_job_endpoint(
    job_id: str,
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> BrainstormJobStatusResponse:
    try:
        return get_brainstorm_job(repo, user_id, job_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/content-sources/extract", response_model=ContentSourceResponse)
def extract_content_source_endpoint(payload: ContentSourceExtractRequest) -> ContentSourceResponse:
    try:
        return extract_content_source(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load article: {exc}") from exc


@app.post("/content-items", response_model=ContentItemResponse)
def create_content_item_endpoint(
    payload: ContentItemCreateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ContentItemResponse:
    try:
        return create_content_item(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/users/{user_id}/content-items", response_model=list[ContentItemResponse])
def list_content_items_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ContentItemResponse]:
    try:
        return list_content_items(repo, user_id, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.patch("/content-items/{content_id}", response_model=ContentItemResponse)
def update_content_item_endpoint(
    content_id: str,
    payload: ContentItemUpdateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ContentItemResponse:
    try:
        return update_content_item(repo, content_id, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/carousels", response_model=CarouselResponse)
def create_carousel_endpoint(
    payload: CarouselCreateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CarouselResponse:
    try:
        return create_carousel(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/carousels/generate", response_model=CarouselResponse)
def generate_carousel_endpoint(
    payload: CarouselGenerateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CarouselResponse:
    try:
        return generate_carousel(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/users/{user_id}/carousels", response_model=list[CarouselResponse])
def list_carousels_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CarouselResponse]:
    try:
        return list_carousels(repo, user_id, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.patch("/carousels/{carousel_id}", response_model=CarouselResponse)
def update_carousel_endpoint(
    carousel_id: str,
    payload: CarouselUpdateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CarouselResponse:
    try:
        return update_carousel(repo, carousel_id, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/images/generate", response_model=ImageAssetResponse)
def generate_image_endpoint(
    payload: ImageGenerationRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ImageAssetResponse:
    try:
        return generate_image_asset(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/users/{user_id}/image-assets", response_model=list[ImageAssetResponse])
def list_image_assets_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ImageAssetResponse]:
    try:
        return list_image_assets(repo, user_id, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/assets/{asset_id}/content")
def get_image_asset_content_endpoint(
    asset_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> FileResponse:
    try:
        path, media_type = get_image_asset_path(repo, asset_id)
        return FileResponse(path, media_type=media_type, filename=path.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Image asset not found: {asset_id}") from exc


@app.delete("/users/{user_id}/image-assets/{asset_id}", response_model=DeleteResponse)
def delete_image_asset_endpoint(
    user_id: str,
    asset_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> DeleteResponse:
    try:
        delete_image_asset(repo, user_id, asset_id)
        return DeleteResponse(ok=True, message=f"Deleted image asset {asset_id}.")
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/threads", response_model=list[ThreadSummary])
def list_user_threads(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> list[ThreadSummary]:
    if not repo.get_user(user_id):
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return [thread_summary(thread) for thread in repo.list_threads(user_id, limit)]


@app.get("/users/{user_id}/threads/{thread_id}", response_model=ThreadResponse)
def get_thread(
    user_id: str,
    thread_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    thread = repo.get_thread(user_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")
    return thread_response(thread)


@app.delete("/users/{user_id}/threads/{thread_id}", response_model=DeleteResponse)
def delete_thread(
    user_id: str,
    thread_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> DeleteResponse:
    repo.delete_thread(user_id, thread_id)
    return DeleteResponse(ok=True, message=f"Deleted thread {thread_id}.")


@app.post("/linkedin/posts/publish", response_model=LinkedInPostPublishResponse)
def track_linkedin_post_endpoint(
    payload: LinkedInPostPublishRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> LinkedInPostPublishResponse:
    try:
        return track_published_linkedin_post(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/linkedin/posts/sync-recent", response_model=SyncRecentOwnPostsResponse)
def sync_recent_linkedin_posts_endpoint(
    payload: SyncRecentOwnPostsRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> SyncRecentOwnPostsResponse:
    _require_scraping_enabled()
    try:
        return sync_recent_linkedin_posts(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/users/{user_id}/linkedin/posts", response_model=list[OwnPostResponse])
def list_linkedin_posts_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    source: str | None = Query(default=None),
    window_hours: int | None = Query(default=72, ge=1, le=72),
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=500),
) -> list[OwnPostResponse]:
    try:
        return list_linkedin_posts(repo, user_id, source, window_hours, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/linkedin/posts/{post_id}/engagement/scrape", response_model=PostEngagementScrapeResponse)
def scrape_linkedin_post_engagement_endpoint(
    post_id: str,
    payload: ScrapePostEngagementRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> PostEngagementScrapeResponse:
    _require_scraping_enabled()
    try:
        return scrape_linkedin_post_engagement_service(repo, post_id, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/linkedin/posts/{post_id}/engagers", response_model=list[PostEngagerResponse])
def list_linkedin_post_engagers_endpoint(
    post_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    user_id: str = Query(...),
    engagement_type: str | None = Query(default=None),
    connection_degree: str | None = Query(default=None),
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=500),
) -> list[PostEngagerResponse]:
    try:
        return list_linkedin_post_engagers(repo, user_id, post_id, engagement_type, connection_degree, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/linkedin/prospects", response_model=list[LinkedInProspectResponse])
def list_linkedin_prospects_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    engagement_type: str | None = Query(default=None),
    connection_degree: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LinkedInProspectResponse]:
    try:
        return list_linkedin_prospects(
            repo,
            user_id,
            engagement_type=engagement_type,
            connection_degree=connection_degree,
            search=search,
            limit=limit,
        )
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/linkedin/action-logs", response_model=list[LinkedInActionLogResponse])
def list_linkedin_action_logs_endpoint(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    post_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=500),
) -> list[LinkedInActionLogResponse]:
    try:
        return list_linkedin_action_logs(repo, user_id, post_id, action_type, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/linkedin/actions/comment-replies", response_model=LinkedInActionBatchResponse)
def send_comment_replies_endpoint(
    payload: CommentReplyActionRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> LinkedInActionBatchResponse:
    if not payload.dry_run:
        _require_scraping_enabled()
    try:
        return send_comment_replies(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/linkedin/actions/connection-requests", response_model=LinkedInActionBatchResponse)
def send_connection_requests_endpoint(
    payload: ConnectionRequestActionRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> LinkedInActionBatchResponse:
    if not payload.dry_run:
        _require_scraping_enabled()
    try:
        return send_connection_requests(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/linkedin/actions/dms", response_model=LinkedInActionBatchResponse)
def send_dms_endpoint(
    payload: DmActionRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> LinkedInActionBatchResponse:
    if not payload.dry_run:
        _require_scraping_enabled()
    try:
        return send_dms(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/creators", response_model=CreatorResponse)
def add_creator(
    payload: CreatorCreateRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CreatorResponse:
    try:
        return create_creator(repo, payload.user_id, payload.profile_url)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creators/import", response_model=BulkCreatorImportResponse)
async def import_creators_endpoint(
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    user_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> BulkCreatorImportResponse:
    try:
        content = await file.read()
        return import_creators_from_file(repo, user_id, file.filename or "", content)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creators/import/preview", response_model=BulkCreatorPreviewResponse)
async def preview_creators_import_endpoint(
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    user_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> BulkCreatorPreviewResponse:
    try:
        content = await file.read()
        return preview_creators_from_file(repo, user_id, file.filename or "", content)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creators/profile-details/scrape", response_model=ScrapeCreatorProfilesResponse)
def scrape_creator_profiles_endpoint(
    payload: ScrapeCreatorProfilesRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeCreatorProfilesResponse:
    _require_scraping_enabled()
    try:
        return scrape_creator_profile_details(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/scrape-jobs/creators/profile-details", response_model=ScrapeJobStartResponse)
def start_creator_profile_scrape_job_endpoint(
    payload: ScrapeCreatorProfilesRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeJobStartResponse:
    _require_scraping_enabled()
    try:
        return start_profile_scrape_job(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/creators", response_model=list[CreatorResponse])
def list_creators(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=1000),
) -> list[CreatorResponse]:
    if not repo.get_user(user_id):
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return [CreatorResponse.model_validate(creator) for creator in repo.list_creators(user_id, limit)]


@app.get("/users/{user_id}/creators/profile-details", response_model=list[CreatorProfileDetailsResponse])
def list_user_creator_profile_details(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=500),
) -> list[CreatorProfileDetailsResponse]:
    try:
        return list_creator_profile_details(repo, user_id, limit)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/creators/{creator_id}/profile-details", response_model=CreatorProfileDetailsResponse)
def get_user_creator_profile_details(
    user_id: str,
    creator_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> CreatorProfileDetailsResponse:
    try:
        return get_creator_profile_details(repo, user_id, creator_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.delete("/users/{user_id}/creators/{creator_id}", response_model=DeleteResponse)
def delete_creator(
    user_id: str,
    creator_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> DeleteResponse:
    try:
        return delete_creator_with_activities(repo, user_id, creator_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/creators/scrape", response_model=ScrapeCreatorsResponse)
def scrape_creators_endpoint(
    payload: ScrapeCreatorsRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeCreatorsResponse:
    _require_scraping_enabled()
    try:
        from app.api.services import scrape_creators

        return scrape_creators(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/creators/scrape/recent-24h", response_model=RecentScrapeCreatorsResponse)
def scrape_recent_creators_endpoint(
    payload: RecentScrapeCreatorsRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> RecentScrapeCreatorsResponse:
    _require_scraping_enabled()
    try:
        return scrape_creators_recent_24h(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/scrape-jobs/creators/recent-24h", response_model=ScrapeJobStartResponse)
def start_recent_creators_scrape_job_endpoint(
    payload: RecentScrapeCreatorsRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeJobStartResponse:
    _require_scraping_enabled()
    try:
        return start_recent_scrape_job(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/scrape-jobs/{job_id}", response_model=ScrapeJobStatusResponse)
def get_scrape_job_endpoint(
    job_id: str,
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeJobStatusResponse:
    try:
        return get_scrape_job(repo, user_id, job_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/creators/{creator_id}/activities", response_model=list[ActivityResponse])
def list_creator_activities(
    user_id: str,
    creator_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> list[ActivityResponse]:
    if not repo.get_creator(user_id, creator_id):
        raise HTTPException(status_code=404, detail=f"Creator not found: {creator_id}")
    return [
        ActivityResponse.model_validate(activity)
        for activity in repo.list_creator_activities(user_id, creator_id, limit)
    ]


@app.get("/users/{user_id}/activities", response_model=list[ActivityResponse])
def list_user_activities(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[ActivityResponse]:
    return list_all_activities(repo, user_id, limit)


@app.get("/users/{user_id}/activities/recent-24h", response_model=RecentActivitiesResponse)
def list_recent_user_activities(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=500),
    window_hours: int = Query(default=24, ge=1, le=72),
) -> RecentActivitiesResponse:
    try:
        return list_recent_activities_from_db(repo, user_id, limit, window_hours)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.get("/users/{user_id}/engagements/comments", response_model=list[CommentedActivityResponse])
def list_user_commented_activities(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=10, ge=1, le=100),
) -> list[CommentedActivityResponse]:
    return list_commented_activities(repo, user_id, limit)
