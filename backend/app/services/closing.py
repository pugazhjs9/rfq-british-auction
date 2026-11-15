from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import Clock
from app.engine import AuctionStatus
from app.messages import render
from app.models import AuctionEvent, Bid, EventType, Rfq
from app.services.standings import current_ranking
from app.visibility import View


def finalize_due_auctions(session: Session, clock: Clock, limit: int = 100) -> list[tuple[int, EventType]]:
    """Write the closing event for every auction whose time has run out.

    This is bookkeeping, not enforcement: bids are already rejected the moment
    the clock passes `current_close_at`, whether or not this job has run.

    SKIP LOCKED leaves alone any auction a bid is holding right now (that bid
    may still extend it). Overlapping runs of this job can't double-close an
    auction because each one only sees rows where `finalized_at` is still NULL.
    The caller commits.
    """
    now = clock.now(session)
    due = session.scalars(
        select(Rfq)
        .where(Rfq.finalized_at.is_(None), Rfq.current_close_at <= now)
        .order_by(Rfq.current_close_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    closed = []
    for rfq in due:
        forced = rfq.status_at(now) is AuctionStatus.FORCE_CLOSED
        event_type = EventType.AUCTION_FORCE_CLOSED if forced else EventType.AUCTION_CLOSED
        session.add(_closing_event(session, rfq, event_type))
        rfq.finalized_at = now
        closed.append((rfq.id, event_type))
    session.flush()
    return closed


def _closing_event(session: Session, rfq: Rfq, event_type: EventType) -> AuctionEvent:
    ranking, standing_bids = current_ranking(session, rfq.id)
    winner = standing_bids[ranking[0].supplier_id] if ranking else None
    bid_count = session.scalar(select(func.count(Bid.id)).where(Bid.rfq_id == rfq.id))
    event = AuctionEvent(
        rfq_id=rfq.id,
        event_type=event_type,
        previous_close_at=rfq.current_close_at,
        new_close_at=rfq.current_close_at,
        details={
            "winner_id": winner.supplier_id if winner else None,
            "total": str(winner.total_amount) if winner else None,
            "suppliers": len(ranking),
            "bids": bid_count,
            "extensions": rfq.extension_count if rfq.british_auction else None,
        },
        created_at=rfq.current_close_at,  # when it closed, not when the job noticed
    )
    event.message = render(event, View(companies={sid: b.supplier.company for sid, b in standing_bids.items()}))
    return event
