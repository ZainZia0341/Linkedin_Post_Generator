from __future__ import annotations

import io
import time
import zipfile

from app.api.schemas import (
    CreatorCreateRequest,
    GenerateCommentRequest,
    GeneratePostRequest,
    MarkCommentedRequest,
    ModifyPostRequest,
    RecentScrapeCreatorsRequest,
    ScrapeCreatorsRequest,
)
from app.api.services import (
    create_creator,
    create_user,
    generate_comment,
    generate_post,
    import_creators_from_file,
    list_commented_activities,
    mark_activity_commented,
    modify_post,
    scrape_creators,
    scrape_creators_recent_24h,
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

    def delete_activity(self, user_id: str, creator_id: str, post_id: str):
        self.activities.pop((user_id, creator_id, post_id), None)

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


def test_api_service_add_creator_duplicate_returns_existing_without_rewrite() -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/theburningmonk/")
    stored = repo.creators[("test-user-1", "theburningmonk")]
    stored["updated_at"] = "kept-updated-at"
    stored["seen_count"] = 7

    duplicate = create_creator(repo, "test-user-1", "linkedin.com/in/theburningmonk/?trk=abc")

    assert duplicate.creator_id == "theburningmonk"
    assert duplicate.updated_at == "kept-updated-at"
    assert duplicate.seen_count == 7
    assert len(repo.creators) == 1


def test_bulk_creator_import_skips_existing_and_file_duplicates() -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/existing-person/")
    content = "\n".join(
        [
            "creator_url",
            "https://www.linkedin.com/in/existing-person/",
            "https://www.linkedin.com/in/new-person/",
            "linkedin.com/in/new-person/?trk=copy",
            "https://www.linkedin.com/",
        ]
    ).encode("utf-8")

    response = import_creators_from_file(repo, "test-user-1", "creators.csv", content)

    assert response.total_urls == 4
    assert [creator.creator_id for creator in response.added_creators] == ["new-person"]
    assert response.skipped_existing_creator_ids == ["existing-person"]
    assert response.skipped_duplicate_creator_ids == ["new-person"]
    assert len(response.errors) == 1
    assert "profile path" in response.errors[0]["message"]


def test_bulk_creator_import_reads_xlsx_upload() -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    buffer = io.BytesIO()
    sheet_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>https://www.linkedin.com/in/sheet-person/</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""
    with zipfile.ZipFile(buffer, "w") as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    response = import_creators_from_file(repo, "test-user-1", "creators.xlsx", buffer.getvalue())

    assert response.errors == []
    assert [creator.creator_id for creator in response.added_creators] == ["sheet-person"]


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


def test_recent_24h_scrape_returns_seen_posts_again_and_filters_old(monkeypatch) -> None:
    repo = MemoryRepo()
    create_user(repo, "test-user-1", {"headline": "AI engineer"}, None)
    create_creator(repo, "test-user-1", "https://www.linkedin.com/in/recent-person/")
    repo.put_activity(
        {
            "user_creator_id": "test-user-1#recent-person",
            "user_id": "test-user-1",
            "creator_id": "recent-person",
            "post_id": "urn:li:activity:recent-seen",
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:recent-seen/",
            "raw_text": "Previously saved version of a recent creator post.",
            "author_name": "Recent Person",
            "posted_at_text": "1h",
            "fetched_at": services.now_iso(),
            "content_hash": "hash-recent-seen",
            "source": "playwright",
            "is_new": True,
            "engagement": {"comment": {"commented": True, "text": "Already commented."}},
        }
    )
    repo.put_activity(
        {
            "user_creator_id": "test-user-1#recent-person",
            "user_id": "test-user-1",
            "creator_id": "recent-person",
            "post_id": "urn:li:activity:stale-stored",
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:stale-stored/",
            "raw_text": "Stored post from an old scrape that should be pruned.",
            "author_name": "Recent Person",
            "posted_at_text": "1h",
            "fetched_at": "2020-01-01T00:00:00+00:00",
            "content_hash": "hash-stale-stored",
            "source": "playwright",
            "is_new": True,
        }
    )

    def fake_fetch(profile_url: str, max_posts: int = 5):
        return [
            {
                "post_id": "urn:li:activity:recent-seen",
                "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:recent-seen/",
                "raw_text": "Updated scrape text for the same recent creator post.",
                "author_name": "Recent Person",
                "posted_at_text": "2h",
                "source": "playwright",
            },
            {
                "post_id": "urn:li:activity:recent-new",
                "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:recent-new/",
                "raw_text": "A brand new creator post from inside the last hour.",
                "author_name": "Recent Person",
                "posted_at_text": "45m",
                "source": "playwright",
            },
            {
                "post_id": "urn:li:activity:old-post",
                "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:old-post/",
                "raw_text": "An older creator post that should not be returned.",
                "author_name": "Recent Person",
                "posted_at_text": "2d",
                "source": "playwright",
            },
        ]

    monkeypatch.setattr(services, "LINKEDIN_AUTOMATION_MODE", "logged_out")
    monkeypatch.setattr(services, "fetch_recent_profile_posts", fake_fetch)

    response = scrape_creators_recent_24h(
        repo,
        RecentScrapeCreatorsRequest(
            user_id="test-user-1",
            creator_ids=["recent-person"],
            max_posts=3,
            window_hours=24,
        ),
    )

    returned = {activity.post_id: activity for activity in response.activities}
    assert set(returned) == {"urn:li:activity:recent-seen", "urn:li:activity:recent-new"}
    assert returned["urn:li:activity:recent-seen"].is_new is False
    assert returned["urn:li:activity:recent-new"].is_new is True
    assert repo.get_activity("test-user-1", "recent-person", "urn:li:activity:old-post") is None
    assert repo.get_activity("test-user-1", "recent-person", "urn:li:activity:stale-stored") is None
    stored_seen = repo.get_activity("test-user-1", "recent-person", "urn:li:activity:recent-seen")
    assert stored_seen["engagement"]["comment"]["commented"] is True
    assert stored_seen["raw_text"] == "Updated scrape text for the same recent creator post."
