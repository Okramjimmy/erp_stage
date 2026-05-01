import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from src.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager for ERP Stage Builder."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Cache is optional, continue without it
            self.redis_client = None

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.redis_client:
            return None

        try:
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        if not self.redis_client:
            return False

        try:
            json_value = json.dumps(value)
            if ttl:
                await self.redis_client.setex(key, ttl, json_value)
            else:
                await self.redis_client.set(key, json_value)
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.redis_client:
            return False

        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a pattern."""
        if not self.redis_client:
            return 0

        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.redis_client:
            return False

        try:
            return await self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def invalidate_master_metadata(self):
        """Invalidate master metadata cache."""
        await self.delete("master_metadata")
        logger.info("Master metadata cache invalidated")

    async def invalidate_stage_cache(self, stage_id: str):
        """Invalidate cache for a specific stage and its affected resources."""
        # Invalidate stage path cache
        await self.delete(f"stage:{stage_id}:path")

        # Invalidate user visible stages cache
        await self.delete_pattern("user:*:visible_stages")

        # Invalidate permission caches for this stage
        await self.delete_pattern(f"permission:*:{stage_id}")

        logger.info(f"Stage cache invalidated for {stage_id}")


# Global cache manager instance
cache = CacheManager()
