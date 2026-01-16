import asyncio
import time
from typing import Any, Dict, Optional

import asyncpg
from fastapi import FastAPI, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from redis.asyncio import Redis

from .config import (
    BACKOFF_BASE_SECONDS,
    DATABASE_URL,
    DLQ_NAME,
    MAX_ATTEMPTS,
    MAX_CONCURRENCY,
    QUEUE_NAME,
    REDIS_URL,
)
from .logger import logger
from .processor import FatalError, RetryableError, evaluate_policy, extract_with_guardrails, rate_limiter, stage_ocr
from .queue import QueueClient, backoff_sleep
from .repository import Repository

app = FastAPI(title="PA Worker", version="0.1.0")

jobs_processed = Counter("jobs_processed_total", "Jobs processed successfully")
jobs_failed = Counter("jobs_failed_total", "Jobs failed")
jobs_retried = Counter("jobs_retried_total", "Jobs retried")
latency_hist = Histogram("job_latency_seconds", "End to end latency", buckets=[0.5, 1, 2, 5, 10, 30])

redis: Optional[Redis] = None
queue: Optional[QueueClient] = None
repo: Optional[Repository] = None
pool: Optional[asyncpg.Pool] = None
worker_task: Optional[asyncio.Task] = None
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


async def process_message(payload: Dict[str, Any]):
    global repo, queue
    assert repo is not None
    assert queue is not None
    job_id = payload.get("job_id")
    request_id = payload.get("request_id")
    start_time = time.time()

    job_row = await repo.get_job(job_id)
    if not job_row:
        logger.warn("Job not found", {"job_id": job_id})
        return

    if job_row["status"] == "completed":
        logger.info("Skipping already completed job", {"job_id": job_id})
        return

    await repo.ensure_request_processing(request_id)
    await repo.increment_attempt(job_id)

    try:
        rate_limiter.check()
        doc_text = await repo.load_document(job_id)
        if not doc_text:
            raise FatalError("document_missing")

        ocr_text = stage_ocr(doc_text)
        evidence, sources, missing = extract_with_guardrails(ocr_text)
        decision, explanation, missing = evaluate_policy(evidence, missing)

        metadata = {
            "attempts": job_row["attempts"] + 1,
            "trace_id": str(job_row["trace_id"]),
            "latency_ms": int((time.time() - start_time) * 1000),
        }

        await repo.write_evidence_pack(
            request_id=request_id,
            decision=decision,
            explanation=explanation,
            metadata=metadata,
            evidence=evidence,
            sources=sources,
            missing_fields=missing,
        )
        await repo.mark_completed(job_id)
        await repo.append_audit(request_id, "worker", "EVIDENCE_PACK_CREATED", {"job_id": job_id})
        jobs_processed.inc()
        latency_hist.observe(time.time() - start_time)
        logger.info("Job processed", {"job_id": job_id, "decision": decision})
    except RetryableError as err:
        jobs_retried.inc()
        if job_row["attempts"] + 1 >= MAX_ATTEMPTS:
            await repo.mark_failed(job_id, str(err))
            await repo.set_request_status(request_id, "failed")
            await queue.push_dlq(payload)  # type: ignore
            jobs_failed.inc()
            logger.error("Job sent to DLQ", {"job_id": job_id, "error": str(err)})
            return
        await repo.reset_to_queue(job_id, str(err))
        await backoff_sleep(job_row["attempts"] + 1, BACKOFF_BASE_SECONDS)
        await queue.push(payload)  # type: ignore
        logger.warn("Job retried", {"job_id": job_id, "error": str(err)})
    except FatalError as err:
        jobs_failed.inc()
        await repo.mark_failed(job_id, str(err))
        await repo.set_request_status(request_id, "failed")
        await queue.push_dlq(payload)  # type: ignore
        logger.error("Fatal error, job to DLQ", {"job_id": job_id, "error": str(err)})
    except Exception as err:  # unexpected
        jobs_failed.inc()
        await repo.mark_failed(job_id, str(err))
        await repo.set_request_status(request_id, "failed")
        await queue.push_dlq(payload)  # type: ignore
        logger.error("Unexpected failure", {"job_id": job_id, "error": str(err)})


async def worker_loop():
    global queue
    assert queue is not None
    while True:
        payload = await queue.pop(timeout=5)
        if not payload:
            continue
        await semaphore.acquire()
        asyncio.create_task(handle_payload(payload))


async def handle_payload(payload: Dict[str, Any]):
    try:
        await process_message(payload)
    finally:
        semaphore.release()


@app.on_event("startup")
async def startup_event():
    global redis, queue, pool, repo, worker_task
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    queue = QueueClient(redis)
    pool = await asyncpg.create_pool(DATABASE_URL)
    repo = Repository(pool)
    worker_task = asyncio.create_task(worker_loop())
    logger.info("Worker started", {"queue": QUEUE_NAME, "dlq": DLQ_NAME})


@app.on_event("shutdown")
async def shutdown_event():
    global redis, pool, worker_task
    if worker_task:
        worker_task.cancel()
    if redis:
        await redis.close()
    if pool:
        await pool.close()


@app.get("/health")
async def health():
    return {"status": "ok", "queue": QUEUE_NAME}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
