import asyncio

from worker.app import main
from worker.app.processor import rate_limiter


class FakeRepo:
    def __init__(self, status: str, attempts: int, doc: str):
        self.job = {"job_id": "job-1", "request_id": "req-1", "status": status, "attempts": attempts, "trace_id": "t1"}
        self.doc = doc
        self.last_error = None
        self.packs = []
        self.audit = []
        self.request_status = None

    async def get_job(self, job_id: str):
        return self.job

    async def ensure_request_processing(self, request_id: str):
        self.request_status = "processing"

    async def increment_attempt(self, job_id: str):
        self.job["attempts"] += 1
        self.job["status"] = "processing"

    async def load_document(self, job_id: str):
        return self.doc

    async def write_evidence_pack(self, request_id, decision, explanation, metadata, evidence, sources, missing_fields):
        self.packs.append(decision)
        return "pack-1", decision

    async def mark_completed(self, job_id: str):
        self.job["status"] = "completed"

    async def append_audit(self, request_id: str, actor: str, action: str, metadata=None):
        self.audit.append(action)

    async def mark_failed(self, job_id: str, error: str):
        self.job["status"] = "failed"
        self.last_error = error

    async def reset_to_queue(self, job_id: str, error: str):
        self.job["status"] = "queued"
        self.last_error = error

    async def set_request_status(self, request_id: str, status: str):
        self.request_status = status


class FakeQueue:
    def __init__(self):
        self.sent = []
        self.dlq = []

    async def push(self, payload):
        self.sent.append(payload)

    async def push_dlq(self, payload):
        self.dlq.append(payload)


def setup_globals(repo, queue):
    main.repo = repo
    main.queue = queue
    rate_limiter.events.clear()


def test_idempotency_skip_completed():
    repo = FakeRepo(status="completed", attempts=1, doc="ok text")
    queue = FakeQueue()
    setup_globals(repo, queue)
    asyncio.run(main.process_message({"job_id": "job-1", "request_id": "req-1"}))
    assert repo.job["status"] == "completed"
    assert queue.sent == []
    assert queue.dlq == []


def test_retry_to_dlq_after_max_attempts():
    # attempts set near max so next retry triggers DLQ
    repo = FakeRepo(status="queued", attempts=2, doc="FAIL_OCR")
    queue = FakeQueue()
    setup_globals(repo, queue)
    asyncio.run(main.process_message({"job_id": "job-1", "request_id": "req-1"}))
    assert repo.job["status"] == "failed"
    assert len(queue.dlq) == 1
