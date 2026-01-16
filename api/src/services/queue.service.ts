import { Injectable, OnModuleDestroy } from '@nestjs/common';
import Redis from 'ioredis';
import { config } from '../config';
import { logger } from '../utils/logger';

@Injectable()
export class QueueService implements OnModuleDestroy {
  private readonly redis: Redis;
  private readonly queueName: string;

  constructor() {
    this.queueName = config.queueName;
    this.redis = new Redis(config.redisUrl);
    this.redis.on('error', (err) => logger.error('Redis error', { error: err.message }));
  }

  async onModuleDestroy() {
    await this.redis.quit();
  }

  async publishDocument(job: { job_id: string; request_id: string; trace_id: string }) {
    await this.redis.lpush(this.queueName, JSON.stringify(job));
    logger.info('Enqueued document job', { job_id: job.job_id, request_id: job.request_id });
  }
}
