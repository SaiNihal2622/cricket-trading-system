"""Redis client for real-time state caching"""
import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis = None

# Cache key prefixes
MATCH_STATE_KEY = "match:state:{match_id}"
ODDS_KEY = "odds:latest:{match_id}"
SIGNAL_KEY = "signal:latest:{match_id}"
TELEGRAM_SIGNALS_KEY = "telegram:signals:{match_id}"
WIN_PROB_KEY = "ml:win_prob:{match_id}"


async def init_redis():
    global redis_client
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=settings.REDIS_POOL_SIZE,
    )
    await redis_client.ping()
    logger.info("Redis connection established")


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()


async def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Ensure init_redis() is called before handling requests.")
    return redis_client


class RedisCache:
    """High-level Redis caching operations"""

    def __init__(self, client: aioredis.Redis):
        self.client = client

    async def set_match_state(self, match_id: int, state: dict, ttl: int = 300):
        key = MATCH_STATE_KEY.format(match_id=match_id)
        await self.client.setex(key, ttl, json.dumps(state))

    async def get_match_state(self, match_id: int) -> Optional[dict]:
        key = MATCH_STATE_KEY.format(match_id=match_id)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def set_odds(self, match_id: int, odds: dict, ttl: int = 60):
        key = ODDS_KEY.format(match_id=match_id)
        await self.client.setex(key, ttl, json.dumps(odds))
        # Push to time series list (keep last 100)
        ts_key = f"odds:history:{match_id}"
        await self.client.lpush(ts_key, json.dumps(odds))
        await self.client.ltrim(ts_key, 0, 99)

    async def get_odds(self, match_id: int) -> Optional[dict]:
        key = ODDS_KEY.format(match_id=match_id)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def get_odds_history(self, match_id: int, limit: int = 20) -> list:
        key = f"odds:history:{match_id}"
        items = await self.client.lrange(key, 0, limit - 1)
        return [json.loads(i) for i in items]

    async def set_signal(self, match_id: int, signal: dict, ttl: int = 120):
        key = SIGNAL_KEY.format(match_id=match_id)
        await self.client.setex(key, ttl, json.dumps(signal))
        # Signal history
        hist_key = f"signal:history:{match_id}"
        await self.client.lpush(hist_key, json.dumps(signal))
        await self.client.ltrim(hist_key, 0, 49)

    async def get_signal(self, match_id: int) -> Optional[dict]:
        key = SIGNAL_KEY.format(match_id=match_id)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def get_signal_history(self, match_id: int, limit: int = 20) -> list:
        key = f"signal:history:{match_id}"
        items = await self.client.lrange(key, 0, limit - 1)
        return [json.loads(i) for i in items]

    async def set_telegram_signals(self, match_id: int, signals: list, ttl: int = 300):
        key = TELEGRAM_SIGNALS_KEY.format(match_id=match_id)
        await self.client.setex(key, ttl, json.dumps(signals))

    async def get_telegram_signals(self, match_id: int) -> list:
        key = TELEGRAM_SIGNALS_KEY.format(match_id=match_id)
        data = await self.client.get(key)
        return json.loads(data) if data else []

    async def set_win_probability(self, match_id: int, prob: dict, ttl: int = 60):
        key = WIN_PROB_KEY.format(match_id=match_id)
        await self.client.setex(key, ttl, json.dumps(prob))

    async def get_win_probability(self, match_id: int) -> Optional[dict]:
        key = WIN_PROB_KEY.format(match_id=match_id)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def publish(self, channel: str, message: dict):
        """Publish to pub/sub channel"""
        await self.client.publish(channel, json.dumps(message))

    async def subscribe(self, *channels):
        """Subscribe to pub/sub channels"""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub
