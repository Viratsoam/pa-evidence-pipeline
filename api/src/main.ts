import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import { config } from './config';
import { logger } from './utils/logger';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { logger: false });
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true }));
  app.setGlobalPrefix('');

  await app.listen(config.port);
  logger.info('API service started', { port: config.port });
}

bootstrap().catch((err) => {
  logger.error('API bootstrap failed', { error: err.message });
  process.exit(1);
});
