from __future__ import annotations

from app import extension_scraping


class ExtensionQueueRepo:
    def __init__(self) -> None:
        self.tasks: dict[tuple[str, str], dict] = {}
        self.clients: dict[tuple[str, str], dict] = {}

    def put_extension_client(self, user_id: str, client: dict):
        self.clients[(user_id, client["extension_id"])] = dict(client)

    def put_extension_task(self, user_id: str, task: dict):
        self.tasks[(user_id, task["task_id"])] = dict(task)
        return self.tasks[(user_id, task["task_id"])]

    def get_extension_task(self, user_id: str, task_id: str):
        return self.tasks.get((user_id, task_id))

    def list_extension_tasks(self, user_id: str):
        return [
            dict(task)
            for (stored_user_id, _), task in self.tasks.items()
            if stored_user_id == user_id
        ]


def test_extension_tasks_are_enqueued_per_creator(monkeypatch):
    repo = ExtensionQueueRepo()
    monkeypatch.setattr(extension_scraping, "get_repository", lambda: repo)

    tasks = extension_scraping.enqueue_extension_scrape_tasks(
        job_id="SCRAPE-1",
        job_type="creator_posts",
        user_id="user-1",
        creators=[
            {"creator_id": "a", "profile_url": "https://www.linkedin.com/in/a/"},
            {"creator_id": "b", "profile_url": "https://www.linkedin.com/in/b/"},
        ],
        max_posts=2,
        window_hours=24,
    )

    assert [task["ordinal"] for task in tasks] == [1, 2]
    assert all(task["total_creators"] == 2 for task in tasks)
    assert all(task["status"] == "queued" for task in tasks)
    assert all(task["job_id"] == "SCRAPE-1" for task in tasks)
    assert all("long_break_every_creators" in task for task in tasks)


def test_extension_claims_oldest_task_first(monkeypatch):
    repo = ExtensionQueueRepo()
    monkeypatch.setattr(extension_scraping, "get_repository", lambda: repo)
    for task in [
        {
            "task_id": "newer",
            "status": "queued",
            "created_at": "2026-07-23T10:01:00+00:00",
            "ordinal": 1,
        },
        {
            "task_id": "older",
            "status": "queued",
            "created_at": "2026-07-23T10:00:00+00:00",
            "ordinal": 1,
        },
    ]:
        repo.put_extension_task("user-1", task)

    claimed = extension_scraping.claim_extension_task("user-1", "chrome-1")

    assert claimed is not None
    assert claimed["task_id"] == "older"
    assert claimed["status"] == "claimed"
    assert repo.get_extension_task("user-1", "older")["attempts"] == 1
