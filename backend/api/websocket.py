"""
WebSocket Handler
Real-time streaming of match state, signals, and odds to frontend
"""
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from database.redis_client import get_redis, RedisCache

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        logger.info(f"WS connected: {channel} ({len(self.active_connections[channel])} clients)")

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            try:
                self.active_connections[channel].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, channel: str, message: dict):
        if channel not in self.active_connections:
            return
        dead = []
        for ws in self.active_connections[channel]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"WS send error: {e}")


manager = ConnectionManager()


@router.websocket("/match/{match_id}")
async def match_websocket(websocket: WebSocket, match_id: int):
    """
    Real-time match state stream.
    Sends state updates every poll interval.
    """
    channel = f"match:{match_id}"
    await manager.connect(websocket, channel)

    redis = await get_redis()
    cache = RedisCache(redis)

    # Send initial state
    state = await cache.get_match_state(match_id)
    if state:
        await manager.send_personal(websocket, {
            "type": "match_state",
            "data": state
        })

    # Subscribe to Redis pub/sub
    pubsub = await cache.subscribe(f"match:updates", f"odds:updates", f"signals:new")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            channel_name = message["channel"]

            # Determine message type
            if "match:updates" in channel_name:
                msg_type = "match_state"
            elif "odds:updates" in channel_name:
                msg_type = "odds_update"
            elif "signals:new" in channel_name:
                msg_type = "signal"
            else:
                continue

            await manager.send_personal(websocket, {
                "type": msg_type,
                "data": data
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
        logger.info(f"WS disconnected: match {match_id}")
    except Exception as e:
        logger.error(f"WS error: {e}")
        manager.disconnect(websocket, channel)
    finally:
        await pubsub.unsubscribe()


@router.websocket("/signals")
async def signals_websocket(websocket: WebSocket):
    """
    Global signal stream — all match signals.
    """
    await manager.connect(websocket, "signals")
    redis = await get_redis()
    cache = RedisCache(redis)
    pubsub = await cache.subscribe("signals:new", "telegram:signals")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            await manager.send_personal(websocket, {
                "type": "signal",
                "data": data
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, "signals")
    finally:
        await pubsub.unsubscribe()


@router.websocket("/odds/{match_id}")
async def odds_websocket(websocket: WebSocket, match_id: int):
    """Real-time odds stream for a match"""
    channel = f"odds:{match_id}"
    await manager.connect(websocket, channel)
    redis = await get_redis()
    cache = RedisCache(redis)

    # Send current odds
    current = await cache.get_odds(match_id)
    if current:
        await manager.send_personal(websocket, {
            "type": "odds_snapshot",
            "data": current
        })

    pubsub = await cache.subscribe("odds:updates")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            if data.get("match_id") == match_id:
                await manager.send_personal(websocket, {
                    "type": "odds_update",
                    "data": data
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    finally:
        await pubsub.unsubscribe()


@router.websocket("/agent")
async def agent_websocket(websocket: WebSocket):
    """
    Real-time agent action stream.
    Streams all autonomous agent decisions, trades, and status changes
    to the frontend Agent Command Center.
    """
    channel = "agent"
    await manager.connect(websocket, channel)
    redis = await get_redis()
    cache = RedisCache(redis)
    pubsub = await cache.subscribe("agent:actions")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            await manager.send_personal(websocket, {
                "type": "agent_action",
                "data": data
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
        logger.info("WS disconnected: agent")
    except Exception as e:
        logger.error(f"Agent WS error: {e}")
        manager.disconnect(websocket, channel)
    finally:
        await pubsub.unsubscribe()
