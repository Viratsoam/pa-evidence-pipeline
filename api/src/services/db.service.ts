import { Injectable, OnModuleDestroy } from '@nestjs/common';
import { Pool, PoolClient, QueryResult, QueryResultRow } from 'pg';
import { config } from '../config';
import { logger } from '../utils/logger';

@Injectable()
export class DbService implements OnModuleDestroy {
  private readonly pool: Pool;

  constructor() {
    this.pool = new Pool({ connectionString: config.databaseUrl });
    this.pool.on('error', (err: Error) => {
      logger.error('DB pool error', { error: err.message });
    });
  }

  async onModuleDestroy() {
    await this.pool.end();
  }

  async query<T extends QueryResultRow = QueryResultRow>(text: string, params: any[] = []): Promise<QueryResult<T>> {
    return this.pool.query<T>(text, params);
  }

  async getClient(): Promise<PoolClient> {
    return this.pool.connect();
  }
}
