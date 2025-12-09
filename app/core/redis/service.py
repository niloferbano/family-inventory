from typing import Any, Optional
from app.core.redis.client import redis_client


class RedisService:

    @staticmethod
    async def set(key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a value with optional TTL (seconds)."""
        return await redis_client.set(key, value, ex=ttl)

    @staticmethod
    async def get(key: str) -> Optional[str]:
        """Get value by key."""
        return await redis_client.get(key)

    @staticmethod
    async def delete(key: str) -> int:
        """Delete a key. Returns number of keys removed."""
        return await redis_client.delete(key)

    @staticmethod
    async def exists(key: str) -> bool:
        """Check if key exists."""
        return await redis_client.exists(key) == 1

    @staticmethod
    async def expire(key: str, ttl: int) -> bool:
        """Update TTL of a key."""
        return await redis_client.expire(key, ttl)

    @staticmethod
    async def incr(key: str) -> int:
        """Increment an integer key."""
        return await redis_client.incr(key)

    @staticmethod
    async def publish(channel: str, message: str) -> int:
        """Publish a message (future IoT use)."""
        return await redis_client.publish(channel, message)
    
