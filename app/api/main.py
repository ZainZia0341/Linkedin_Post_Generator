from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from app.api.schemas import (
    ActivityResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    BrainstormRequest,
    BrainstormResponse,
    CreatorCreateRequest,
    CreatorResponse,
    DeleteResponse,
    GenerateFromActivityRequest,
    GeneratePostRequest,
    ModifyPostRequest,
    ScrapeCreatorsRequest,
    ScrapeCreatorsResponse,
    ThreadResponse,
    ThreadSummary,
    UserCreateRequest,
    UserDataResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.api.services import (
    SAVED_ACTIONS,
    brainstorm,
    create_creator,
    create_user,
    generate_from_activity,
    generate_post,
    list_all_activities,
    modify_post,
    seed_default_users,
    thread_response,
    thread_summary,
    update_user,
    user_response,
)
from app.config import API_LIST_LIMIT, PROVIDER_MODELS
from app.db.dynamodb import DynamoRepository, DynamoUnavailable, get_repository
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/actions", response_model=list[str])
def list_saved_actions() -> list[str]:
    return SAVED_ACTIONS


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
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> UserDataResponse:
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    creators = [CreatorResponse.model_validate(creator) for creator in repo.list_creators(user_id, limit)]
    threads = [thread_summary(thread) for thread in repo.list_threads(user_id, limit)]
    activities = list_all_activities(repo, user_id, limit)
    return UserDataResponse(
        user=user_response(user),
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


@app.post("/posts/modify", response_model=ThreadResponse)
def modify_post_endpoint(
    payload: ModifyPostRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    try:
        return modify_post(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/posts/from-creator-activity", response_model=ThreadResponse)
def generate_from_creator_activity_endpoint(
    payload: GenerateFromActivityRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ThreadResponse:
    try:
        return generate_from_activity(repo, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc


@app.post("/ideas/brainstorm", response_model=BrainstormResponse)
def brainstorm_endpoint(
    payload: BrainstormRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> BrainstormResponse:
    try:
        return brainstorm(repo, payload)
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


@app.get("/users/{user_id}/creators", response_model=list[CreatorResponse])
def list_creators(
    user_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> list[CreatorResponse]:
    if not repo.get_user(user_id):
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return [CreatorResponse.model_validate(creator) for creator in repo.list_creators(user_id, limit)]


@app.delete("/users/{user_id}/creators/{creator_id}", response_model=DeleteResponse)
def delete_creator(
    user_id: str,
    creator_id: str,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> DeleteResponse:
    repo.delete_creator(user_id, creator_id)
    return DeleteResponse(ok=True, message=f"Deleted creator {creator_id}.")


@app.post("/creators/scrape", response_model=ScrapeCreatorsResponse)
def scrape_creators_endpoint(
    payload: ScrapeCreatorsRequest,
    repo: Annotated[DynamoRepository, Depends(repo_dependency)],
) -> ScrapeCreatorsResponse:
    try:
        from app.api.services import scrape_creators

        return scrape_creators(repo, payload)
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
    limit: int = Query(default=API_LIST_LIMIT, ge=1, le=100),
) -> list[ActivityResponse]:
    return list_all_activities(repo, user_id, limit)
