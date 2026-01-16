from typing import Any, Dict, Optional, Tuple

import asyncpg
import json

from .logger import logger


class Repository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_job(self, job_id: str) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow(
            "SELECT job_id, request_id, status, attempts, trace_id FROM core.document_jobs WHERE job_id=$1",
            job_id,
        )

    async def increment_attempt(self, job_id: str):
        await self.pool.execute(
            "UPDATE core.document_jobs SET attempts = attempts + 1, status='processing', updated_at=now() WHERE job_id=$1",
            job_id,
        )

    async def mark_failed(self, job_id: str, error: str):
        await self.pool.execute(
            "UPDATE core.document_jobs SET status='failed', last_error=$2, updated_at=now() WHERE job_id=$1",
            job_id,
            error,
        )

    async def mark_completed(self, job_id: str):
        await self.pool.execute(
            "UPDATE core.document_jobs SET status='completed', updated_at=now() WHERE job_id=$1",
            job_id,
        )

    async def reset_to_queue(self, job_id: str, error: str):
        await self.pool.execute(
            "UPDATE core.document_jobs SET status='queued', last_error=$2, updated_at=now() WHERE job_id=$1",
            job_id,
            error,
        )

    async def load_document(self, job_id: str) -> Optional[str]:
        row = await self.pool.fetchrow("SELECT content FROM phi.documents WHERE job_id=$1", job_id)
        return row["content"] if row else None

    async def write_evidence_pack(
        self,
        request_id: str,
        decision: str,
        explanation: str,
        metadata: Dict[str, Any],
        evidence: Dict[str, Any],
        sources: Dict[str, Any],
        missing_fields: list[str],
    ) -> Tuple[str, str]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                metadata_json = json.dumps(metadata) if metadata is not None else None
                evidence_json = json.dumps(evidence) if evidence is not None else None
                sources_json = json.dumps(sources) if sources is not None else None

                pack_row = await conn.fetchrow(
                    """
                    INSERT INTO core.evidence_packs (request_id, decision, explanation, metadata)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    request_id,
                    decision,
                    explanation,
                    metadata_json,
                )
                pack_id = pack_row["id"]
                await conn.execute(
                    """
                    INSERT INTO phi.evidence_details (pack_id, evidence, sources, missing_fields)
                    VALUES ($1, $2, $3, $4)
                    """,
                    pack_id,
                    evidence_json,
                    sources_json,
                    missing_fields,
                )
                await conn.execute(
                    """
                    UPDATE core.pa_requests
                    SET latest_pack_id=$2, status='completed', updated_at=now()
                    WHERE id=$1
                    """,
                    request_id,
                    pack_id,
                )
                return pack_id, decision

    async def append_audit(self, request_id: str, actor: str, action: str, metadata: Dict[str, Any] | None = None):
        metadata_json = json.dumps(metadata) if metadata is not None else None
        await self.pool.execute(
            "INSERT INTO core.audit_events (request_id, actor, action, metadata) VALUES ($1, $2, $3, $4)",
            request_id,
            actor,
            action,
            metadata_json,
        )

    async def set_request_status(self, request_id: str, status: str):
        await self.pool.execute(
            "UPDATE core.pa_requests SET status=$2, updated_at=now() WHERE id=$1",
            request_id,
            status,
        )

    async def ensure_request_processing(self, request_id: str):
        await self.set_request_status(request_id, "processing")
