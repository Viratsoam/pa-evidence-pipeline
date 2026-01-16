import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Headers,
  UseGuards,
  Req,
} from '@nestjs/common';
import { PaRequestsService } from '../services/pa-requests.service';
import { CreatePaRequestDto } from '../dto/create-pa-request.dto';
import { UploadDocumentDto } from '../dto/upload-document.dto';
import { ApiKeyGuard } from '../guards/api-key.guard';

@Controller('/v1/pa-requests')
@UseGuards(ApiKeyGuard)
export class PaRequestsController {
  constructor(private readonly service: PaRequestsService) {}

  @Post()
  async create(@Body() _body: CreatePaRequestDto, @Req() req: any) {
    return this.service.createRequest(req.actor);
  }

  @Post('/:requestId/documents')
  async uploadDocument(
    @Param('requestId') requestId: string,
    @Body() body: UploadDocumentDto,
    @Headers('idempotency-key') idempotencyKey: string,
    @Req() req: any,
  ) {
    const key = idempotencyKey || '';
    return this.service.uploadDocument({
      requestId,
      idempotencyKey: key,
      text: body.text,
      actor: req.actor,
    });
  }

  @Get('/:requestId')
  async getRequest(@Param('requestId') requestId: string) {
    return this.service.getRequest(requestId);
  }
}
