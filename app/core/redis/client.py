import redis.asyncio as redis

from app.core.configs.config import settings

redis_client = redis.from_url(settings.CACHE.url, decode_responses=True)
