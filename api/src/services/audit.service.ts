import { Injectable } from '@nestjs/common';
import { DbService } from './db.service';

@Injectable()
export class AuditService {
  constructor(private readonly db: DbService) {}

  async writeEvent(params: {
    requestId: string | null;
    actor: string;
    action: string;
    metadata?: Record<string, unknown>;
  }) {
    const { requestId, actor, action, metadata } = params;
    await this.db.query(
      `INSERT INTO core.audit_events (request_id, actor, action, metadata)
       VALUES ($1, $2, $3, $4)`,
      [requestId, actor, action, metadata ? JSON.stringify(metadata) : null],
    );
  }

  async listByRequest(requestId: string) {
    const result = await this.db.query(
      `SELECT actor, action, metadata, created_at
       FROM core.audit_events
       WHERE request_id = $1
       ORDER BY created_at DESC`,
      [requestId],
    );
    return result.rows;
  }
}
