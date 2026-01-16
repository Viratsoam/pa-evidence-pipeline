import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { config } from '../config';

@Injectable()
export class ApiKeyGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const header = request.headers['x-api-key'] || request.headers['X-API-Key'];
    if (!header || header !== config.apiKey) {
      throw new UnauthorizedException('invalid api key');
    }
    request.actor = 'api-key';
    return true;
  }
}
