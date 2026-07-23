from __future__ import annotations

from decimal import Decimal
import socket
from typing import Any
from urllib.parse import urlparse

from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.config import (
    API_LIST_LIMIT,
    DYNAMODB_AUTO_CREATE_TABLES,
    DYNAMODB_ENDPOINT_URL,
    DYNAMODB_REGION_NAME,
    DYNAMODB_TABLE_PREFIX,
)


def _clean_for_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _clean_for_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_for_dynamodb(item) for item in value]
    return value


def _clean_from_dynamodb(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {key: _clean_from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_from_dynamodb(item) for item in value]
    return value


def _without_keys(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {key: value for key, value in item.items() if key not in {"PK", "SK", "entity_type"}}


class DynamoUnavailable(RuntimeError):
    pass


class DynamoRepository:
    """Single-table DynamoDB repository.

    All user-owned records share USER#{user_id}; entity prefixes in SK provide
    bounded queries without secondary indexes.
    """

    def __init__(self) -> None:
        import boto3

        kwargs: dict[str, Any] = {
            "region_name": DYNAMODB_REGION_NAME,
            "config": Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}),
        }
        if DYNAMODB_ENDPOINT_URL:
            kwargs.update(
                endpoint_url=DYNAMODB_ENDPOINT_URL,
                aws_access_key_id="dummy",
                aws_secret_access_key="dummy",
            )
        self.resource = boto3.resource("dynamodb", **kwargs)
        self.client = self.resource.meta.client
        self.table_name = f"{DYNAMODB_TABLE_PREFIX}_app"

    def ensure_tables(self) -> None:
        if DYNAMODB_ENDPOINT_URL:
            self._assert_endpoint_reachable()
        self._ensure_table()

    def _assert_endpoint_reachable(self) -> None:
        parsed = urlparse(DYNAMODB_ENDPOINT_URL)
        try:
            with socket.create_connection(
                (parsed.hostname or "localhost", parsed.port or (443 if parsed.scheme == "https" else 80)),
                timeout=1,
            ):
                return
        except OSError as exc:
            raise DynamoUnavailable(
                f"DynamoDB Local is not reachable at {DYNAMODB_ENDPOINT_URL}. "
                "From backend/, start it with: docker compose -f docker-compose.dynamodb.yml up -d"
            ) from exc

    def _ensure_table(self) -> None:
        try:
            self.client.describe_table(TableName=self.table_name)
        except self.client.exceptions.ResourceNotFoundException as exc:
            if not DYNAMODB_AUTO_CREATE_TABLES:
                raise DynamoUnavailable(
                    f"DynamoDB table {self.table_name} does not exist. Deploy the Serverless stack "
                    "or enable DYNAMODB_AUTO_CREATE_TABLES for local-only development."
                ) from exc
            self.resource.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            ).wait_until_exists()
        except EndpointConnectionError as exc:
            raise DynamoUnavailable(f"DynamoDB is not reachable at {DYNAMODB_ENDPOINT_URL}.") from exc
        except (BotoCoreError, ClientError) as exc:
            raise DynamoUnavailable(str(exc)) from exc

    @property
    def table(self):
        return self.resource.Table(self.table_name)

    @staticmethod
    def _user_pk(user_id: str) -> str:
        return f"USER#{user_id}"

    def _put(self, pk: str, sk: str, entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
        stored = _clean_for_dynamodb({**item, "PK": pk, "SK": sk, "entity_type": entity_type})
        self.table.put_item(Item=stored)
        return _clean_from_dynamodb(item)

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"PK": pk, "SK": sk}).get("Item")
        return _without_keys(_clean_from_dynamodb(item)) if item else None

    def _query(self, pk: str, prefix: str, limit: int | None = None, scan_forward: bool = False) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(prefix),
            Limit=limit or API_LIST_LIMIT,
            ScanIndexForward=scan_forward,
        )
        return [_without_keys(_clean_from_dynamodb(item)) for item in response.get("Items", [])]

    def put_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return self._put(self._user_pk(user["user_id"]), "PROFILE", "user", user)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._get(self._user_pk(user_id), "PROFILE")

    def list_users(self, limit: int | None = None) -> list[dict[str, Any]]:
        response = self.table.scan(FilterExpression=Attr("entity_type").eq("user"), Limit=limit or API_LIST_LIMIT)
        return [_without_keys(_clean_from_dynamodb(item)) for item in response.get("Items", [])]

    def put_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        return self._put(self._user_pk(thread["user_id"]), f"THREAD#{thread['thread_id']}", "thread", thread)

    def get_thread(self, user_id: str, thread_id: str) -> dict[str, Any] | None:
        return self._get(self._user_pk(user_id), f"THREAD#{thread_id}")

    def list_threads(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self._user_pk(user_id), "THREAD#", limit)

    def delete_thread(self, user_id: str, thread_id: str) -> None:
        self.table.delete_item(Key={"PK": self._user_pk(user_id), "SK": f"THREAD#{thread_id}"})

    def put_creator(self, creator: dict[str, Any]) -> dict[str, Any]:
        return self._put(self._user_pk(creator["user_id"]), f"CREATOR#{creator['creator_id']}", "creator", creator)

    def get_creator(self, user_id: str, creator_id: str) -> dict[str, Any] | None:
        return self._get(self._user_pk(user_id), f"CREATOR#{creator_id}")

    def list_creators(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self._user_pk(user_id), "CREATOR#", limit)

    def delete_creator(self, user_id: str, creator_id: str) -> None:
        self.table.delete_item(Key={"PK": self._user_pk(user_id), "SK": f"CREATOR#{creator_id}"})

    def put_activity(self, activity: dict[str, Any]) -> dict[str, Any]:
        sk = f"ACTIVITY#{activity['creator_id']}#{activity['post_id']}"
        return self._put(self._user_pk(activity["user_id"]), sk, "activity", activity)

    def get_activity(self, user_id: str, creator_id: str, post_id: str) -> dict[str, Any] | None:
        return self._get(self._user_pk(user_id), f"ACTIVITY#{creator_id}#{post_id}")

    def delete_activity(self, user_id: str, creator_id: str, post_id: str) -> None:
        self.table.delete_item(Key={"PK": self._user_pk(user_id), "SK": f"ACTIVITY#{creator_id}#{post_id}"})

    def list_creator_activities(self, user_id: str, creator_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self._user_pk(user_id), f"ACTIVITY#{creator_id}#", limit)

    def put_job(self, job: dict[str, Any]) -> dict[str, Any]:
        return self._put(self._user_pk(job["user_id"]), f"JOB#{job['job_id']}", "job", job)

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        return self._get(self._user_pk(user_id), f"JOB#{job_id}")

    def list_jobs(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self._user_pk(user_id), "JOB#", limit)

    @staticmethod
    def _extension_pk(user_id: str) -> str:
        return f"EXTENSION#{user_id}"

    def put_extension_client(self, user_id: str, client: dict[str, Any]) -> dict[str, Any]:
        return self._put(
            self._extension_pk(user_id),
            f"CLIENT#{client['extension_id']}",
            "extension_client",
            client,
        )

    def list_extension_clients(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self._extension_pk(user_id), "CLIENT#", limit, scan_forward=True)

    def put_extension_task(self, user_id: str, task: dict[str, Any]) -> dict[str, Any]:
        return self._put(
            self._extension_pk(user_id),
            f"TASK#{task['task_id']}",
            "extension_task",
            task,
        )

    def get_extension_task(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        return self._get(self._extension_pk(user_id), f"TASK#{task_id}")

    def list_extension_tasks(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "KeyConditionExpression": (
                Key("PK").eq(self._extension_pk(user_id))
                & Key("SK").begins_with("TASK#")
            ),
            "ScanIndexForward": True,
        }
        if limit is not None:
            query["Limit"] = limit

        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query)
            items.extend(
                _without_keys(_clean_from_dynamodb(item))
                for item in response.get("Items", [])
            )
            if limit is not None and len(items) >= limit:
                return items[:limit]
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            query["ExclusiveStartKey"] = last_key

    def delete_extension_task(self, user_id: str, task_id: str) -> None:
        self.table.delete_item(
            Key={"PK": self._extension_pk(user_id), "SK": f"TASK#{task_id}"}
        )


_repository: DynamoRepository | None = None


def get_repository() -> DynamoRepository:
    global _repository
    if _repository is None:
        _repository = DynamoRepository()
    return _repository
