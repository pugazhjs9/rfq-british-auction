"""Live updates over Redis pub/sub.

Whoever changes an auction (an API replica or the Celery worker) publishes a
small message after committing. Every API replica relays messages to its own
WebSocket clients, who then refetch. Messages are hints, not data, so a
dropped one only delays a refresh. The frontend also polls as a fallback.
"""

import json
import logging
from datetime import datetime
from typing import Protocol

import redis

from app.config import settings

log = logging.getLogger(__name__)

ALL_AUCTIONS_CHANNEL = "auctions"


def auction_channel(rfq_id: int) -> str:
    return f"auctions:{rfq_id}"


class Publisher(Protocol):
    def publish(self, rfq_id: int, events: list[str], current_close_at: datetime | None) -> None: ...


class RedisPublisher:
    def __init__(self, url: str):
        self._redis = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)

    def publish(self, rfq_id: int, events: list[str], current_close_at: datetime | None) -> None:
        message = json.dumps(
            {
                "rfq_id": rfq_id,
                "events": events,
                "current_close_at": current_close_at.isoformat() if current_close_at else None,
            }
        )
        try:
            with self._redis.pipeline(transaction=False) as pipe:
                pipe.publish(auction_channel(rfq_id), message)
                pipe.publish(ALL_AUCTIONS_CHANNEL, message)
                pipe.execute()
        except redis.RedisError:
            # The write is already committed; a missed hint must not fail the request.
            log.warning("Could not publish update for RFQ %s", rfq_id, exc_info=True)


publisher = RedisPublisher(settings.redis_url)
