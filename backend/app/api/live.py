import asyncio
import contextlib

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from app.config import settings
from app.realtime import ALL_AUCTIONS_CHANNEL, auction_channel

router = APIRouter()


@router.websocket("/ws/rfqs")
async def all_auctions_feed(websocket: WebSocket):
    await _relay(websocket, ALL_AUCTIONS_CHANNEL)


@router.websocket("/ws/rfqs/{rfq_id}")
async def auction_feed(websocket: WebSocket, rfq_id: int):
    await _relay(websocket, auction_channel(rfq_id))


async def _relay(websocket: WebSocket, channel: str) -> None:
    """Forward every message on a Redis channel to one WebSocket client."""
    await websocket.accept()
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
    except RedisError:
        await websocket.close(code=1011, reason="Live updates unavailable")
        await client.aclose()
        return

    async def forward() -> None:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])

    async def until_disconnect() -> None:
        # Clients never send anything; receive() just tells us when they leave.
        while True:
            await websocket.receive_text()

    tasks = [asyncio.create_task(forward()), asyncio.create_task(until_disconnect())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RedisError, RuntimeError):
                await task
        await pubsub.aclose()
        await client.aclose()
