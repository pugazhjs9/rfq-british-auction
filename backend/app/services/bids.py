from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import Clock
from app.engine import AuctionStatus, Extension, RankingChange, Standing, apply_bid, decide_extension
from app.errors import Conflict, Forbidden, InvalidInput, NotFound
from app.formatting import format_inr
from app.messages import render
from app.models import AuctionEvent, Bid, EventType, Rfq, User, UserRole
from app.schemas import BidCreate
from app.services.standings import current_ranking
from app.visibility import View


@dataclass
class BidOutcome:
    rfq: Rfq
    bid: Bid
    change: RankingChange
    extension: Extension | None
    events: list[AuctionEvent] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return self.change.new_position + 1

    @property
    def previous_rank(self) -> int | None:
        old = self.change.old_position
        return None if old is None else old + 1


def submit_bid(
    session: Session, clock: Clock, rfq_id: int, supplier: User, data: BidCreate
) -> BidOutcome:
    """Validate a bid, rank it, and extend the auction if a trigger fires.

    The caller commits. Everything happens while holding a row lock on the RFQ,
    so bids on the same auction are applied one at a time and each sees the
    ranking and close time left by the previous one.
    """
    if supplier.role is not UserRole.SUPPLIER:
        raise Forbidden("Only suppliers can place bids")

    rfq = session.scalar(select(Rfq).where(Rfq.id == rfq_id).with_for_update())
    if rfq is None:
        raise NotFound("RFQ not found")

    # Read the clock only once the lock is held. A bid that queued behind
    # another one must be judged by when it actually got its turn.
    now = clock.now(session)
    status = rfq.status_at(now)
    if status is AuctionStatus.UPCOMING:
        raise Conflict("Bidding hasn't opened yet", code="AUCTION_NOT_STARTED")
    if status is not AuctionStatus.ACTIVE:
        raise Conflict("Bidding has closed for this RFQ", code="AUCTION_CLOSED")

    total = data.freight_charges + data.origin_charges + data.destination_charges
    if total <= 0:
        raise InvalidInput("The quote total must be more than zero", field="freight_charges")
    if data.quote_valid_until < rfq.pickup_date:
        raise InvalidInput(
            "The quote must stay valid at least until the pickup date", field="quote_valid_until"
        )

    ranking, standing_bids = current_ranking(session, rfq.id)
    previous = standing_bids.get(supplier.id)
    if previous is not None and total >= previous.total_amount:
        raise Conflict(
            f"Your new total must be lower than your current bid of {format_inr(previous.total_amount)}",
            code="BID_NOT_LOWER",
        )

    bid = Bid(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        carrier_name=data.carrier_name,
        freight_charges=data.freight_charges,
        origin_charges=data.origin_charges,
        destination_charges=data.destination_charges,
        transit_time_days=data.transit_time_days,
        quote_valid_until=data.quote_valid_until,
        created_at=now,
    )
    session.add(bid)
    session.flush()

    change = apply_bid(ranking, Standing(supplier.id, total, now, bid.id))
    outcome = BidOutcome(rfq=rfq, bid=bid, change=change, extension=None)
    # Messages are stored with every name visible; app.messages explains why.
    companies = {sid: b.supplier.company for sid, b in standing_bids.items()} | {supplier.id: supplier.company}
    everyone = View(companies=companies)
    outcome.events.append(
        _logged(
            AuctionEvent(
                rfq_id=rfq.id,
                event_type=EventType.BID_SUBMITTED,
                bid_id=bid.id,
                actor_id=supplier.id,
                details={
                    "total": str(total),
                    "carrier": bid.carrier_name,
                    "rank": outcome.rank,
                    "previous_rank": outcome.previous_rank,
                },
                created_at=now,
            ),
            everyone,
        )
    )

    rules = rfq.rules  # None unless this is a British auction
    if rules is not None:
        extension = decide_extension(now, rfq.current_close_at, rfq.forced_close_at, rules, change)
        if extension is not None:
            outcome.extension = extension
            outcome.events.append(_logged(_extension_event(rfq, bid, change, extension, now), everyone))
            if extension.extended:
                rfq.current_close_at = extension.new_close_at
                rfq.extension_count += 1

    session.add_all(outcome.events)
    session.flush()
    return outcome


def _extension_event(
    rfq: Rfq, bid: Bid, change: RankingChange, extension: Extension, now: datetime
) -> AuctionEvent:
    """Written before current_close_at moves, so 'before close' is measured from the old close."""
    return AuctionEvent(
        rfq_id=rfq.id,
        event_type=EventType.EXTENDED if extension.extended else EventType.EXTENSION_SKIPPED,
        bid_id=bid.id,
        actor_id=bid.supplier_id,
        previous_close_at=extension.previous_close_at,
        new_close_at=extension.new_close_at,
        details={
            "trigger": rfq.trigger_type.value,
            "rank": change.new_position + 1,
            "previous_rank": None if change.old_position is None else change.old_position + 1,
            "previous_l1_id": change.previous_l1.supplier_id if change.previous_l1 else None,
            "before_close_seconds": int((rfq.current_close_at - now).total_seconds()),
            "requested_seconds": rfq.extension_minutes * 60,
            "applied_seconds": int(extension.applied.total_seconds()),
            "capped": extension.capped,
        },
        created_at=now,
    )


def _logged(event: AuctionEvent, view: View) -> AuctionEvent:
    event.message = render(event, view)
    return event
