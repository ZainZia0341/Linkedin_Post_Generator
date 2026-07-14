from __future__ import annotations

from decimal import Decimal
import socket
from typing import Any
from urllib.parse import urlparse

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
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _clean_from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_from_dynamodb(item) for item in value]
    return value


class DynamoUnavailable(RuntimeError):
    pass


class DynamoRepository:
    def __init__(self) -> None:
        import boto3

        resource_kwargs: dict[str, Any] = {
            "region_name": DYNAMODB_REGION_NAME,
            "config": Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}),
        }
        if DYNAMODB_ENDPOINT_URL:
            resource_kwargs.update(
                {
                    "endpoint_url": DYNAMODB_ENDPOINT_URL,
                    "aws_access_key_id": "dummy",
                    "aws_secret_access_key": "dummy",
                }
            )

        self.resource = boto3.resource(
            "dynamodb",
            **resource_kwargs,
        )
        self.client = self.resource.meta.client
        self.users_table_name = f"{DYNAMODB_TABLE_PREFIX}_users"
        self.threads_table_name = f"{DYNAMODB_TABLE_PREFIX}_threads"
        self.creators_table_name = f"{DYNAMODB_TABLE_PREFIX}_creators"
        self.activities_table_name = f"{DYNAMODB_TABLE_PREFIX}_activities"

    def ensure_tables(self) -> None:
        if DYNAMODB_ENDPOINT_URL:
            self._assert_endpoint_reachable()
        for table_name, partition_key, sort_key in (
            (self.users_table_name, "user_id", None),
            (self.threads_table_name, "user_id", "thread_id"),
            (self.creators_table_name, "user_id", "creator_id"),
            (self.activities_table_name, "user_creator_id", "post_id"),
        ):
            self._ensure_table(table_name, partition_key, sort_key)

    def _assert_endpoint_reachable(self) -> None:
        parsed = urlparse(DYNAMODB_ENDPOINT_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError as exc:
            raise DynamoUnavailable(
                f"DynamoDB Local is not reachable at {DYNAMODB_ENDPOINT_URL}. "
                "From backend/, start it with: docker compose -f docker-compose.dynamodb.yml up -d"
            ) from exc

    def _ensure_table(self, table_name: str, partition_key: str, sort_key: str | None) -> None:
        try:
            self.client.describe_table(TableName=table_name)
            return
        except self.client.exceptions.ResourceNotFoundException as exc:
            if not DYNAMODB_AUTO_CREATE_TABLES:
                raise DynamoUnavailable(
                    f"DynamoDB table {table_name} does not exist. Deploy the Serverless stack "
                    "or enable DYNAMODB_AUTO_CREATE_TABLES for local-only development."
                ) from exc
            try:
                key_schema = [{"AttributeName": partition_key, "KeyType": "HASH"}]
                attributes = [{"AttributeName": partition_key, "AttributeType": "S"}]
                if sort_key:
                    key_schema.append({"AttributeName": sort_key, "KeyType": "RANGE"})
                    attributes.append({"AttributeName": sort_key, "AttributeType": "S"})

                self.resource.create_table(
                    TableName=table_name,
                    KeySchema=key_schema,
                    AttributeDefinitions=attributes,
                    BillingMode="PAY_PER_REQUEST",
                ).wait_until_exists()
                print(f"Created DynamoDB table: {table_name}")
                return
            except (BotoCoreError, ClientError) as create_exc:
                raise DynamoUnavailable(str(create_exc)) from create_exc
        except EndpointConnectionError as exc:
            raise DynamoUnavailable(
                f"DynamoDB Local is not reachable at {DYNAMODB_ENDPOINT_URL}. "
                "From backend/, start it with: docker compose -f docker-compose.dynamodb.yml up -d"
            ) from exc
        except (BotoCoreError, ClientError) as exc:
            raise DynamoUnavailable(str(exc)) from exc

    def _table(self, table_name: str):
        return self.resource.Table(table_name)

    def _put(self, table_name: str, item: dict[str, Any]) -> dict[str, Any]:
        item = _clean_for_dynamodb(item)
        self._table(table_name).put_item(Item=item)
        return _clean_from_dynamodb(item)

    def _get(self, table_name: str, key: dict[str, str]) -> dict[str, Any] | None:
        response = self._table(table_name).get_item(Key=key)
        item = response.get("Item")
        return _clean_from_dynamodb(item) if item else None

    def _query(
        self,
        table_name: str,
        key_name: str,
        key_value: str,
        limit: int | None = None,
        scan_forward: bool = False,
    ) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        response = self._table(table_name).query(
            KeyConditionExpression=Key(key_name).eq(key_value),
            Limit=limit or API_LIST_LIMIT,
            ScanIndexForward=scan_forward,
        )
        return [_clean_from_dynamodb(item) for item in response.get("Items", [])]

    def _scan(self, table_name: str, limit: int | None = None) -> list[dict[str, Any]]:
        response = self._table(table_name).scan(Limit=limit or API_LIST_LIMIT)
        return [_clean_from_dynamodb(item) for item in response.get("Items", [])]

    def put_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return self._put(self.users_table_name, user)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._get(self.users_table_name, {"user_id": user_id})

    def list_users(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self._scan(self.users_table_name, limit)

    def put_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        return self._put(self.threads_table_name, thread)

    def get_thread(self, user_id: str, thread_id: str) -> dict[str, Any] | None:
        return self._get(self.threads_table_name, {"user_id": user_id, "thread_id": thread_id})

    def list_threads(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self.threads_table_name, "user_id", user_id, limit)

    def delete_thread(self, user_id: str, thread_id: str) -> None:
        self._table(self.threads_table_name).delete_item(Key={"user_id": user_id, "thread_id": thread_id})

    def put_creator(self, creator: dict[str, Any]) -> dict[str, Any]:
        return self._put(self.creators_table_name, creator)

    def get_creator(self, user_id: str, creator_id: str) -> dict[str, Any] | None:
        return self._get(self.creators_table_name, {"user_id": user_id, "creator_id": creator_id})

    def list_creators(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._query(self.creators_table_name, "user_id", user_id, limit)

    def delete_creator(self, user_id: str, creator_id: str) -> None:
        self._table(self.creators_table_name).delete_item(Key={"user_id": user_id, "creator_id": creator_id})

    def put_activity(self, activity: dict[str, Any]) -> dict[str, Any]:
        return self._put(self.activities_table_name, activity)

    def get_activity(self, user_id: str, creator_id: str, post_id: str) -> dict[str, Any] | None:
        return self._get(
            self.activities_table_name,
            {"user_creator_id": f"{user_id}#{creator_id}", "post_id": post_id},
        )

    def list_creator_activities(
        self,
        user_id: str,
        creator_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._query(
            self.activities_table_name,
            "user_creator_id",
            f"{user_id}#{creator_id}",
            limit,
        )


_repository: DynamoRepository | None = None


def get_repository() -> DynamoRepository:
    global _repository
    if _repository is None:
        _repository = DynamoRepository()
    return _repository
