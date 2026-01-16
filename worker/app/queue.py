import asyncio
import json
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from .config import QUEUE_NAME, DLQ_NAME
from .logger import logger


class QueueClient:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.queue_name = QUEUE_NAME
        self.dlq_name = DLQ_NAME

    async def pop(self, timeout: int = 5) -> Optional[Dict[str, Any]]:
        item = await self.redis.brpop(self.queue_name, timeout=timeout)
        if not item:
            return None
        _, payload = item
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.error("Failed to decode queue payload", {"payload": payload})
            return None

    async def push(self, payload: Dict[str, Any]):
        await self.redis.lpush(self.queue_name, json.dumps(payload))

    async def push_dlq(self, payload: Dict[str, Any]):
        await self.redis.lpush(self.dlq_name, json.dumps(payload))
        logger.warn("Sent job to DLQ", {"job_id": payload.get("job_id")})


async def backoff_sleep(attempt: int, base: float):
    delay = base * (2 ** (attempt - 1))
    await asyncio.sleep(delay)
