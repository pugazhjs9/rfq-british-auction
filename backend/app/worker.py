"""Celery app. Run with: celery -A app.worker worker --beat"""

from celery import Celery

from app.clock import DbClock
from app.config import settings
from app.db import SessionLocal
from app.realtime import publisher
from app.services.closing import finalize_due_auctions

celery_app = Celery("auctions", broker=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "finalize-closed-auctions": {
            "task": "auctions.finalize_closed",
            "schedule": settings.finalize_interval_seconds,
        },
    },
)


@celery_app.task(name="auctions.finalize_closed")
def finalize_closed_auctions() -> int:
    with SessionLocal() as session:
        closed = finalize_due_auctions(session, DbClock())
        session.commit()
        rfqs_closed = [(rfq_id, event_type.value) for rfq_id, event_type in closed]
    for rfq_id, event_type in rfqs_closed:
        publisher.publish(rfq_id, [event_type], None)
    return len(rfqs_closed)
