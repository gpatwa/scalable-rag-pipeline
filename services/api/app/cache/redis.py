# services/api/app/cache/redis.py
import redis.asyncio as redis
from services.api.app.config import settings

class RedisClient:
    """
    Singleton Redis connection pool.
    Used for Rate Limiting and Semantic Cache storage.
    """
    def __init__(self):
        self.redis = None

    async def connect(self):
        if not self.redis:
            # decode_responses=True means we get Strings back, not Bytes
            self.redis = redis.from_url(
                settings.REDIS_URL, 
                encoding="utf-8", 
                decode_responses=True
            )

    async def close(self):
        if self.redis:
            await self.redis.close()

    def get_client(self):
        """Returns the raw redis client instance"""
        return self.redis

# Global instance
redis_client = RedisClient()