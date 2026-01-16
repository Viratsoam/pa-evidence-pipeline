import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { AuditService } from '../services/audit.service';
import { ApiKeyGuard } from '../guards/api-key.guard';

@Controller('/v1/audit')
@UseGuards(ApiKeyGuard)
export class AuditController {
  constructor(private readonly audit: AuditService) {}

  @Get()
  async list(@Query('request_id') requestId: string) {
    if (!requestId) {
      return [];
    }
    return this.audit.listByRequest(requestId);
  }
}
