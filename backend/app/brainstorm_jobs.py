from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import os
import time
from uuid import uuid4

from app.api.schemas import (
    BrainstormJobStartResponse,
    BrainstormJobStatusResponse,
    BrainstormRequest,
    BrainstormResponse,
)
from app.db.dynamodb import DynamoRepository

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="brainstorm-job")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _run(repo: DynamoRepository, job_id: str, request: BrainstormRequest) -> None:
    from app.api.services import brainstorm

    job = repo.get_job(request.user_id, job_id)
    if not job:
        return
    started = time.monotonic()
    job.update(status="running", started_at=_now(), updated_at=_now())
    repo.put_job(job)
    try:
        result = brainstorm(repo, request)
        job.update(
            status="succeeded",
            completed_at=_now(),
            updated_at=_now(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            result=result.model_dump(),
            error="",
        )
    except Exception as exc:
        job.update(
            status="failed",
            completed_at=_now(),
            updated_at=_now(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            error=str(exc),
        )
    repo.put_job(job)


def start_brainstorm_job(repo: DynamoRepository, request: BrainstormRequest) -> BrainstormJobStartResponse:
    timestamp = _now()
    job_id = f"BRAINSTORM-{uuid4()}"
    job = {
        "job_id": job_id,
        "job_type": "brainstorm",
        "user_id": request.user_id,
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
        "started_at": "",
        "completed_at": "",
        "elapsed_seconds": None,
        "error": "",
        "result": {},
        "request": request.model_dump(),
    }
    repo.put_job(job)
    worker_name = os.getenv("BRAINSTORM_WORKER_FUNCTION_NAME", "").strip()
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME") and worker_name:
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=worker_name,
            InvocationType="Event",
            Payload=json.dumps({"job_id": job_id, "request": request.model_dump()}).encode("utf-8"),
        )
    else:
        _EXECUTOR.submit(_run, repo, job_id, request)
    return BrainstormJobStartResponse(job_id=job_id, user_id=request.user_id, status="queued", created_at=timestamp)


def get_brainstorm_job(repo: DynamoRepository, user_id: str, job_id: str) -> BrainstormJobStatusResponse:
    job = repo.get_job(user_id, job_id)
    if not job or job.get("job_type") != "brainstorm":
        raise KeyError(f"Brainstorm job not found: {job_id}")
    result = BrainstormResponse.model_validate(job["result"]) if job.get("result") else None
    return BrainstormJobStatusResponse(
        job_id=job_id,
        user_id=user_id,
        status=str(job.get("status", "queued")),
        created_at=str(job.get("created_at", "")),
        started_at=str(job.get("started_at", "")),
        completed_at=str(job.get("completed_at", "")),
        elapsed_seconds=job.get("elapsed_seconds"),
        error=str(job.get("error", "")),
        result=result,
    )


def run_brainstorm_worker(event: dict) -> None:
    from app.db.dynamodb import get_repository

    request = BrainstormRequest.model_validate(event["request"])
    _run(get_repository(), str(event["job_id"]), request)
