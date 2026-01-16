import * as process from 'process';

export const config = {
  port: parseInt(process.env.PORT || '3000', 10),
  databaseUrl: process.env.DATABASE_URL || 'postgres://appuser:appsecret@localhost:5432/appdb',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  apiKey: process.env.API_KEY || 'dev-api-key',
  queueName: process.env.QUEUE_NAME || 'document_uploaded',
  dlqName: process.env.DLQ_NAME || 'document_uploaded_dlq',
};
