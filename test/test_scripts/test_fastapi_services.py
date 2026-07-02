from __future__ import annotations

import time

from app.api.schemas import (
    CreatorCreateRequest,
    GenerateCommentRequest,
    GeneratePostRequest,
    MarkCommentedRequest,
    ModifyPostRequest,
    ScrapeCreatorsRequest,
)
from app.api.services import (
    create_creator,
    create_user,
    generate_comment,
    generate_post,
    list_commented_activities,
    mark_activity_commented,
    modify_post,
    scrape_creators,
)
import app.api.services as services
from app.writing_style_extract import get_builtin_writing_style


class MemoryRepo:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.threads: dict[tuple[str, str], dict] = {}
        self.creators: dict[tuple[str, str], dict] = {}
        self.activities: dict[tuple[str, str, str], dict] = {}

    def get_user(self, user_id: str):
        return self.users.get(user_id)

    def put_user(self, user: dict):
        self.users[user["user_id"]] = dict(user)
        return self.users[user["user_id"]]

    def put_thread(self, thread: dict):
        self.threads[(thread["user_id"], thread["thread_id"])] = dict(thread)
        return self.threads[(thread["user_id"], thread["thread_id"])]

    def get_thread(self, user_id: str, thread_id: str):
        return self.threads.get((user_id, thread_id))

    def get_creator(self, user_id: str, creator_id: str):
        return self.creators.get((user_id, creator_id))

    def put_creator(self, creator: dict):
        self.creators[(creator["user_id"], creator["creator_id"])] = dict(creator)
        return self.creators[(creator["user_id"], creator["creator_id"])]

    def list_creators(self, user_id: str, limit: int | None = None):
        creators = [creator for (stored_user_id, _), creator in self.creators.items() if stored_user_id == user_id]
        return creators[: limit or 10]

    def put_activity(self, activity: dict):
        key = (activity["user_id"], activity["creator_id"], activity["post_id"])
        self.activities[key] = dict(activity)
        return self.activities[key]

    def get_activity(self, user_id: str, creator_id: str, post_id: str):
        return self.activities.get((user_id, creator_id, post_id))

    def list_creator_activities(self, user_id: str, creator_id: str, limit: int | None = None):
        activities = [
            activity
            for (stored_user_id, stored_creator_id, _), activity in self.activities.items()
            if stored_user_id == user_id and stored_creator_id == creator_id
        ]
        return activities[: limit or 10]


def test_api_service_generate_and_modify_offline() -> None:
    repo = MemoryRepo()
    create_user(
        repo,
        "test-user-1",
        {
            "full_name": "Test User",
            "headline": "AI engineer",
            "skills": ["Python", "FastAPI"],
        },
        get_builtin_writing_style("Clear Builder").model_dump(),
    )

    generated = generate_post(
        repo,
        GeneratePostRequest(
            user_id="test-user-1",
            idea="FastAPI and DynamoDB local for AI content tools",
            generation_style="Create a post about a topic",
        ),
    )
    assert generated.thread_id
    assert generated.current_post
    assert "#" in generated.current_post
    assert generated.provider == "gemini"
    assert generated.model == "gemini-3.1-flash-lite"

    modified = modify_post(
        repo,
        ModifyPostRequest(
            user_id="test-user-1",
            thread_id=generated.thread_id,
            modification_message="Make the post shorter",
        ),
    )
    assert modified.modification_count == 1
    assert modified.current_post


def test_api_service_add_creator_normalizes_url() -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    creator = create_creator(repo, "test-user-1", "linkedin.com/in/theburningmonk/?trk=abc")
    assert creator.creator_id == "theburningmonk"
    assert creator.profile_url == "https://www.linkedin.com/in/theburningmonk/"


def test_generate_post_request_does_not_expose_llm_credentials() -> None:
    properties = GeneratePostRequest.model_json_schema()["properties"]
    assert "provider" not in properties
    assert "model" not in properties
    assert "api_key" not in properties


def test_comment_generation_and_tracking_offline() -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/shubhamsaboo/")
    repo.put_activity(
        {
            "user_creator_id": "test-user-1#shubhamsaboo",
            "user_id": "test-user-1",
            "creator_id": "shubhamsaboo",
            "post_id": "urn:li:activity:1",
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
            "raw_text": "A practical creator post about running coding agents in one terminal with persistent sessions.",
            "author_name": "Shubham Saboo",
            "posted_at_text": "1d",
            "fetched_at": "2026-07-02T00:00:00+00:00",
            "content_hash": "hash-1",
            "source": "playwright",
            "is_new": True,
        }
    )

    draft = generate_comment(
        repo,
        GenerateCommentRequest(
            user_id="test-user-1",
            creator_id="shubhamsaboo",
            post_id="urn:li:activity:1",
            comment_topic="Expert Insight",
        ),
    )
    assert draft.comment
    assert draft.comment_topic == "Expert Insight"
    assert draft.commented is False

    marked = mark_activity_commented(
        repo,
        MarkCommentedRequest(
            user_id="test-user-1",
            creator_id="shubhamsaboo",
            post_id="urn:li:activity:1",
            commented=True,
            comment_text=draft.comment,
        ),
    )
    assert marked.commented is True

    commented = list_commented_activities(repo, "test-user-1", limit=10)
    assert len(commented) == 1
    assert commented[0].post_id == "urn:li:activity:1"
    assert commented[0].comment


def test_scrape_creators_uses_one_worker_in_burner_mode(monkeypatch) -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/creator-one/")
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/creator-two/")

    active = 0
    max_active = 0

    def fake_fetch(profile_url: str, max_posts: int = 5):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.02)
        active -= 1
        post_id = profile_url.rstrip("/").split("/")[-1]
        return [
            {
                "post_id": f"urn:li:activity:{post_id}",
                "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{post_id}/",
                "raw_text": f"A saved post from {post_id} about practical AI workflows.",
                "author_name": post_id,
                "posted_at_text": "1d",
                "source": "playwright",
            }
        ]

    monkeypatch.setattr(services, "LINKEDIN_AUTOMATION_MODE", "burner")
    monkeypatch.setattr(services, "SCRAPE_MAX_WORKERS", 2)
    monkeypatch.setattr(services, "fetch_recent_profile_posts", fake_fetch)

    response = scrape_creators(
        repo,
        ScrapeCreatorsRequest(
            user_id="test-user-1",
            creator_ids=["creator-one", "creator-two"],
            max_posts=1,
        ),
    )

    assert max_active == 1
    assert response.errors == []
    assert len(response.new_activities) == 2
