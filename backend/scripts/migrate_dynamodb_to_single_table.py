"""Idempotently copy the legacy four-table data into the single app table."""

from __future__ import annotations

import argparse
from typing import Any, Iterable

import boto3


def scan_all(table: Any) -> Iterable[dict[str, Any]]:
    response = table.scan()
    yield from response.get("Items", [])
    while response.get("LastEvaluatedKey"):
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        yield from response.get("Items", [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, help="For example: linkedin_post_generator_dev")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--endpoint-url")
    args = parser.parse_args()
    kwargs: dict[str, Any] = {"region_name": args.region}
    if args.endpoint_url:
        kwargs.update(endpoint_url=args.endpoint_url, aws_access_key_id="dummy", aws_secret_access_key="dummy")
    resource = boto3.resource("dynamodb", **kwargs)
    target = resource.Table(f"{args.prefix}_app")
    sources = {
        "user": resource.Table(f"{args.prefix}_users"),
        "thread": resource.Table(f"{args.prefix}_threads"),
        "creator": resource.Table(f"{args.prefix}_creators"),
        "activity": resource.Table(f"{args.prefix}_activities"),
    }
    copied = 0
    with target.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
        for entity_type, table in sources.items():
            for source in scan_all(table):
                item = dict(source)
                if entity_type == "user":
                    user_id, sk = str(item["user_id"]), "PROFILE"
                elif entity_type == "thread":
                    user_id, sk = str(item["user_id"]), f"THREAD#{item['thread_id']}"
                elif entity_type == "creator":
                    user_id, sk = str(item["user_id"]), f"CREATOR#{item['creator_id']}"
                else:
                    user_id, creator_id = str(item["user_creator_id"]).split("#", 1)
                    item.setdefault("user_id", user_id)
                    item.setdefault("creator_id", creator_id)
                    sk = f"ACTIVITY#{creator_id}#{item['post_id']}"
                item.update(PK=f"USER#{user_id}", SK=sk, entity_type=entity_type)
                batch.put_item(Item=item)
                copied += 1
    print(f"Copied {copied} records into {args.prefix}_app.")


if __name__ == "__main__":
    main()
