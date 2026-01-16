import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { DbService } from './db.service';
import { QueueService } from './queue.service';
import { AuditService } from './audit.service';
import { logger } from '../utils/logger';

export interface EvidencePack {
  id: string;
  decision: string;
  explanation: string | null;
  metadata: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
  sources: Record<string, unknown> | null;
  missing_fields: string[] | null;
}

@Injectable()
export class PaRequestsService {
  constructor(
    private readonly db: DbService,
    private readonly queue: QueueService,
    private readonly audit: AuditService,
  ) {}

  async createRequest(actor: string) {
    const result = await this.db.query<{ id: string }>(
      `INSERT INTO core.pa_requests (status) VALUES ('pending') RETURNING id`,
    );
    const requestId = result.rows[0].id;
    await this.audit.writeEvent({ requestId, actor, action: 'PA_REQUEST_CREATED' });
    logger.info('PA request created', { request_id: requestId });
    return { request_id: requestId };
  }

  async uploadDocument(params: {
    requestId: string;
    idempotencyKey: string;
    text: string;
    actor: string;
  }) {
    const { requestId, idempotencyKey, text, actor } = params;
    if (!text || text.trim().length === 0) {
      throw new BadRequestException('text is required');
    }
    if (!idempotencyKey || idempotencyKey.trim().length === 0) {
      throw new BadRequestException('Idempotency-Key header is required');
    }
    // ensure request exists
    const request = await this.db.query('SELECT id FROM core.pa_requests WHERE id = $1', [requestId]);
    if (request.rowCount === 0) {
      throw new NotFoundException('request not found');
    }

    const client = await this.db.getClient();
    try {
      await client.query('BEGIN');
      const existing = await client.query<{ job_id: string; trace_id: string }>(
        `SELECT job_id, trace_id FROM core.document_jobs
         WHERE request_id = $1 AND idempotency_key = $2
         FOR UPDATE`,
        [requestId, idempotencyKey],
      );
      if ((existing?.rowCount ?? 0) > 0) {
        await client.query('COMMIT');
        return { job_id: existing.rows[0].job_id, request_id: requestId };
      }

      const jobRes = await client.query<{ job_id: string; trace_id: string }>(
        `INSERT INTO core.document_jobs (request_id, idempotency_key, status, attempts)
         VALUES ($1, $2, 'queued', 0)
         RETURNING job_id, trace_id`,
        [requestId, idempotencyKey],
      );

      const job = jobRes.rows[0];
      await client.query(
        `INSERT INTO phi.documents (job_id, request_id, content) VALUES ($1, $2, $3)`,
        [job.job_id, requestId, text],
      );

      await client.query('COMMIT');

      await this.audit.writeEvent({
        requestId,
        actor,
        action: 'DOCUMENT_UPLOADED',
        metadata: { job_id: job.job_id },
      });

      await this.queue.publishDocument({
        job_id: job.job_id,
        request_id: requestId,
        trace_id: job.trace_id,
      });

      return { job_id: job.job_id, request_id: requestId };
    } catch (err: any) {
      await client.query('ROLLBACK');
      logger.error('Failed to upload document', { error: err.message, request_id: requestId });
      throw err;
    } finally {
      client.release();
    }
  }

  async getRequest(requestId: string): Promise<{ id: string; status: string; evidence_pack: EvidencePack | null }> {
    const result = await this.db.query(
      `SELECT r.id,
              r.status,
              p.id as pack_id,
              p.decision,
              p.explanation,
              p.metadata,
              ed.evidence,
              ed.sources,
              ed.missing_fields
       FROM core.pa_requests r
       LEFT JOIN core.evidence_packs p ON r.latest_pack_id = p.id
       LEFT JOIN phi.evidence_details ed ON ed.pack_id = p.id
       WHERE r.id = $1`,
      [requestId],
    );

    if (result.rowCount === 0) {
      throw new NotFoundException('request not found');
    }

    const row = result.rows[0];
    let pack: EvidencePack | null = null;
    if (row.pack_id) {
      pack = {
        id: row.pack_id,
        decision: row.decision,
        explanation: row.explanation,
        metadata: row.metadata,
        evidence: row.evidence,
        sources: row.sources,
        missing_fields: row.missing_fields,
      };
    }

    return { id: row.id, status: row.status, evidence_pack: pack };
  }
}
