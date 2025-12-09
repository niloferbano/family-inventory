from app.core.redis.service import RedisService

async def get_cache() -> RedisService:
    return RedisService()