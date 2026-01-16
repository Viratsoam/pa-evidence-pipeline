import { Module } from '@nestjs/common';
import { PaRequestsController } from './controllers/pa-requests.controller';
import { PaRequestsService } from './services/pa-requests.service';
import { DbService } from './services/db.service';
import { QueueService } from './services/queue.service';
import { AuditController } from './controllers/audit.controller';
import { AuditService } from './services/audit.service';
import { ApiKeyGuard } from './guards/api-key.guard';

@Module({
  controllers: [PaRequestsController, AuditController],
  providers: [PaRequestsService, DbService, QueueService, AuditService, ApiKeyGuard],
})
export class AppModule {}
