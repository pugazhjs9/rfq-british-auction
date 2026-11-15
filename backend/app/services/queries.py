"""Read models for the listing and details pages, shaped for whoever is viewing."""

from collections import Counter
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.engine import AuctionStatus
from app.errors import NotFound
from app.messages import render
from app.models import AuctionEvent, Bid, Rfq, User, UserRole
from app.schemas import BidOut, EventOut, RankedBidOut, RfqDetailOut, RfqSummaryOut, UserOut
from app.services.standings import current_ranking
from app.visibility import View, assign_aliases

# Listing order: live auctions first (closing soonest), then upcoming (opening
# soonest), then finished ones (most recently closed).
_STATUS_ORDER = {
    AuctionStatus.ACTIVE: 0,
    AuctionStatus.UPCOMING: 1,
    AuctionStatus.CLOSED: 2,
    AuctionStatus.FORCE_CLOSED: 2,
}


def list_auctions(session: Session, now: datetime, viewer: User | None) -> list[RfqSummaryOut]:
    stats = (
        select(
            Bid.rfq_id,
            func.min(Bid.total_amount).label("lowest_bid"),
            func.count(Bid.id).label("bid_count"),
            func.count(func.distinct(Bid.supplier_id)).label("supplier_count"),
        )
        .group_by(Bid.rfq_id)
        .subquery()
    )
    # The single cheapest bid on an RFQ always belongs to L1: each supplier's
    # bids only go down, and ties go to whoever bid first.
    leader = (
        select(Bid.rfq_id, Bid.supplier_id.label("l1_id"), User.company.label("l1_company"))
        .join(User, User.id == Bid.supplier_id)
        .distinct(Bid.rfq_id)
        .order_by(Bid.rfq_id, Bid.total_amount, Bid.created_at, Bid.id)
        .subquery()
    )
    first_quotes = (
        select(Bid.rfq_id, Bid.total_amount)
        .distinct(Bid.rfq_id, Bid.supplier_id)
        .order_by(Bid.rfq_id, Bid.supplier_id, Bid.created_at, Bid.id)
        .subquery()
    )
    best_first = (
        select(first_quotes.c.rfq_id, func.min(first_quotes.c.total_amount).label("best_first_quote"))
        .group_by(first_quotes.c.rfq_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Rfq,
            stats.c.lowest_bid,
            stats.c.bid_count,
            stats.c.supplier_count,
            leader.c.l1_id,
            leader.c.l1_company,
            best_first.c.best_first_quote,
        )
        .outerjoin(stats, stats.c.rfq_id == Rfq.id)
        .outerjoin(leader, leader.c.rfq_id == Rfq.id)
        .outerjoin(best_first, best_first.c.rfq_id == Rfq.id)
    ).all()

    view = View.of(viewer)
    my_ranks = {}
    if viewer is not None and viewer.role is UserRole.SUPPLIER:
        my_ranks = dict(session.execute(_ranks_of(viewer.id)).tuples().all())

    summaries = [
        _summary(
            rfq,
            now,
            lowest_bid=lowest,
            l1_supplier=l1_company if l1_id is not None and view.sees(l1_id) else None,
            bid_count=bids or 0,
            supplier_count=suppliers or 0,
            best_first_quote=best_first_quote,
            my_rank=my_ranks.get(rfq.id),
        )
        for rfq, lowest, bids, suppliers, l1_id, l1_company, best_first_quote in rows
    ]
    summaries.sort(key=_listing_key)
    return summaries


def auction_detail(session: Session, rfq_id: int, now: datetime, viewer: User | None) -> RfqDetailOut:
    rfq = session.get(Rfq, rfq_id, options=[joinedload(Rfq.buyer)], populate_existing=True)
    if rfq is None:
        raise NotFound("RFQ not found")

    ranking, standing_bids = current_ranking(session, rfq.id)
    all_bids = session.scalars(
        select(Bid)
        .options(joinedload(Bid.supplier))
        .where(Bid.rfq_id == rfq.id)
        .order_by(Bid.total_amount, Bid.created_at, Bid.id)
    ).all()
    in_bid_order = sorted(all_bids, key=lambda b: (b.created_at, b.id))
    view = View.of(
        viewer,
        companies={b.supplier_id: b.supplier.company for b in all_bids},
        aliases=assign_aliases(b.supplier_id for b in in_bid_order),
    )
    revisions = Counter(b.supplier_id for b in all_bids)
    rank_by_bid = {s.bid_id: position for position, s in enumerate(ranking, start=1)}
    first_quotes: dict[int, Decimal] = {}
    for b in in_bid_order:
        first_quotes.setdefault(b.supplier_id, b.total_amount)

    ranked = [
        RankedBidOut(
            **bid_out(standing_bids[s.supplier_id], view).model_dump(exclude={"rank"}),
            rank=position,
            revisions=revisions[s.supplier_id],
        )
        for position, s in enumerate(ranking, start=1)
    ]
    events = session.scalars(
        select(AuctionEvent)
        .options(joinedload(AuctionEvent.actor))
        .where(AuctionEvent.rfq_id == rfq.id)
        .order_by(AuctionEvent.created_at.desc(), AuctionEvent.id.desc())
    ).all()

    leader = standing_bids[ranking[0].supplier_id] if ranking else None
    summary = _summary(
        rfq,
        now,
        lowest_bid=leader.total_amount if leader else None,
        l1_supplier=leader.supplier.company if leader and view.sees(leader.supplier_id) else None,
        bid_count=len(all_bids),
        supplier_count=len(ranking),
        best_first_quote=min(first_quotes.values(), default=None),
        my_rank=next((p for p, s in enumerate(ranking, start=1) if s.supplier_id == view.viewer_id), None),
    )
    return RfqDetailOut(
        **summary.model_dump(),
        pickup_date=rfq.pickup_date,
        buyer=UserOut.model_validate(rfq.buyer),
        ranking=ranked,
        bids=[bid_out(b, view, rank_by_bid.get(b.id)) for b in all_bids],
        events=[event_out(e, view) for e in events],
        server_time=now,
    )


def bid_out(bid: Bid, view: View, rank: int | None = None) -> BidOut:
    """A bid as this viewer may see it.

    Fields are listed one by one, so a column added to bids later isn't sent
    to suppliers by accident.
    """
    visible = view.sees(bid.supplier_id)
    return BidOut(
        id=bid.id,
        supplier=UserOut.model_validate(bid.supplier) if visible else None,
        bidder=view.name(bid.supplier_id),
        carrier_name=bid.carrier_name if visible else None,
        freight_charges=bid.freight_charges,
        origin_charges=bid.origin_charges,
        destination_charges=bid.destination_charges,
        total_amount=bid.total_amount,
        transit_time_days=bid.transit_time_days,
        quote_valid_until=bid.quote_valid_until,
        created_at=bid.created_at,
        rank=rank,
    )


def event_out(event: AuctionEvent, view: View) -> EventOut:
    out = EventOut.model_validate(event)
    if view.sees_everyone:
        return out
    actor = event.actor
    shows_actor = actor is not None and (actor.role is UserRole.BUYER or view.sees(actor.id))
    return out.model_copy(
        update={
            "message": render(event, view),
            "actor": out.actor if shows_actor else None,
            # Details hold supplier ids, and /api/users maps ids to names.
            "details": {},
        }
    )


def _ranks_of(supplier_id: int) -> Select[tuple[int, int]]:
    """(rfq_id, rank) for every RFQ the supplier has bid on.

    Same ranking as engine.rank: each supplier's latest bid, ordered by
    (total, time, id). row_number() is safe because that order has no ties.
    """
    standing = (
        select(Bid.rfq_id, Bid.supplier_id, Bid.total_amount, Bid.created_at, Bid.id)
        .where(Bid.rfq_id.in_(select(Bid.rfq_id).where(Bid.supplier_id == supplier_id)))
        .distinct(Bid.rfq_id, Bid.supplier_id)
        .order_by(Bid.rfq_id, Bid.supplier_id, Bid.created_at.desc(), Bid.id.desc())
        .subquery()
    )
    ranked = select(
        standing.c.rfq_id,
        standing.c.supplier_id,
        func.row_number()
        .over(
            partition_by=standing.c.rfq_id,
            order_by=(standing.c.total_amount, standing.c.created_at, standing.c.id),
        )
        .label("rank"),
    ).subquery()
    return select(ranked.c.rfq_id, ranked.c.rank).where(ranked.c.supplier_id == supplier_id)


def _summary(rfq: Rfq, now: datetime, **stats) -> RfqSummaryOut:
    return RfqSummaryOut(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        status=rfq.status_at(now),
        british_auction=rfq.british_auction,
        bid_start_at=rfq.bid_start_at,
        bid_close_at=rfq.bid_close_at,
        current_close_at=rfq.current_close_at,
        forced_close_at=rfq.forced_close_at,
        trigger_window_minutes=rfq.trigger_window_minutes,
        extension_minutes=rfq.extension_minutes,
        trigger_type=rfq.trigger_type,
        extension_count=rfq.extension_count,
        **stats,
    )


def _listing_key(s: RfqSummaryOut):
    group = _STATUS_ORDER[s.status]
    match s.status:
        case AuctionStatus.ACTIVE:
            moment = s.current_close_at.timestamp()
        case AuctionStatus.UPCOMING:
            moment = s.bid_start_at.timestamp()
        case _:
            moment = -s.current_close_at.timestamp()
    return (group, moment, s.id)
