from __future__ import annotations

from app.api.schemas import CreatorCreateRequest, GeneratePostRequest, ModifyPostRequest
from app.api.services import create_creator, create_user, generate_post, modify_post
from app.writing_style_extract import get_builtin_writing_style


class MemoryRepo:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.threads: dict[tuple[str, str], dict] = {}
        self.creators: dict[tuple[str, str], dict] = {}

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
            provider="groq",
            model="llama-3.3-70b-versatile",
        ),
    )
    assert generated.thread_id
    assert generated.current_post
    assert "#" in generated.current_post
    assert generated.provider == "groq"

    modified = modify_post(
        repo,
        ModifyPostRequest(
            user_id="test-user-1",
            thread_id=generated.thread_id,
            modification_message="Make the post shorter",
            provider="groq",
            model="llama-3.3-70b-versatile",
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
