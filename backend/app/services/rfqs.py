from sqlalchemy.orm import Session

from app.clock import Clock
from app.engine import TriggerType
from app.errors import Forbidden, InvalidInput
from app.models import AuctionEvent, EventType, Rfq, User, UserRole
from app.schemas import RfqCreate

TRIGGER_PHRASES = {
    TriggerType.BID_RECEIVED: "Any bid",
    TriggerType.ANY_RANK_CHANGE: "A bid that changes any supplier's rank",
    TriggerType.L1_CHANGE: "A bid that changes the L1 supplier",
}


def describe_rules(rfq: Rfq) -> str:
    if not rfq.british_auction:
        return "Fixed close: bidding ends at the close time and late bids don't extend it."
    return (
        f"{TRIGGER_PHRASES[rfq.trigger_type]} in the last {rfq.trigger_window_minutes} min "
        f"extends the close by {rfq.extension_minutes} min, never past the forced close time."
    )


def create_rfq(session: Session, clock: Clock, buyer: User, data: RfqCreate) -> Rfq:
    if buyer.role is not UserRole.BUYER:
        raise Forbidden("Only buyers can create RFQs")

    now = clock.now(session)
    if data.bid_close_at <= now:
        raise InvalidInput("Bid close time must be in the future", field="bid_close_at")

    rfq = Rfq(
        name=data.name,
        buyer_id=buyer.id,
        pickup_date=data.pickup_date,
        bid_start_at=data.bid_start_at,
        bid_close_at=data.bid_close_at,
        current_close_at=data.bid_close_at,
        british_auction=data.british_auction,
        forced_close_at=data.forced_close_at,
        trigger_window_minutes=data.trigger_window_minutes,
        extension_minutes=data.extension_minutes,
        trigger_type=data.trigger_type,
    )
    session.add(rfq)
    session.flush()
    session.add(
        AuctionEvent(
            rfq_id=rfq.id,
            event_type=EventType.AUCTION_CREATED,
            actor_id=buyer.id,
            message=f"{buyer.company} created the RFQ. {describe_rules(rfq)}",
            created_at=now,
        )
    )
    session.flush()
    return rfq
