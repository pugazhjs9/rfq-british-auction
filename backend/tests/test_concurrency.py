"""Simultaneous bids on one auction must behave as if they arrived one by one."""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.engine import Standing, TriggerType, apply_bid
from app.models import AuctionEvent, Bid, EventType, Rfq, User, UserRole
from app.schemas import BidCreate, RfqCreate
from app.services.bids import submit_bid
from app.services.rfqs import create_rfq
from tests.conftest import NOW

CLOSE = NOW + timedelta(hours=1)
SUPPLIERS = 8


def setup_auction(session_factory, clock, *, window: int, forced_after: int) -> tuple[int, list[int]]:
    with session_factory() as session:
        buyer = User(name="Buyer", company="Indigo Retail", role=UserRole.BUYER)
        suppliers = [User(name=f"S{i}", company=f"Supplier {i}", role=UserRole.SUPPLIER) for i in range(SUPPLIERS)]
        session.add_all([buyer, *suppliers])
        session.flush()
        rfq = create_rfq(
            session,
            clock,
            buyer,
            RfqCreate(
                name="Concurrency test lane",
                bid_start_at=NOW,
                bid_close_at=CLOSE,
                forced_close_at=CLOSE + timedelta(minutes=forced_after),
                pickup_date=(NOW + timedelta(days=5)).date(),
                trigger_window_minutes=window,
                extension_minutes=5,
                trigger_type=TriggerType.BID_RECEIVED,
            ),
        )
        session.commit()
        return rfq.id, [s.id for s in suppliers]


def bid_simultaneously(session_factory, clock, rfq_id: int, supplier_ids: list[int]) -> None:
    """Every thread opens its session, then all of them submit at the same instant."""
    barrier = threading.Barrier(len(supplier_ids))

    def place(index_and_supplier):
        index, supplier_id = index_and_supplier
        with session_factory() as session:
            supplier = session.get(User, supplier_id)
            data = BidCreate(
                carrier_name="Maersk",
                freight_charges=Decimal(100_000 - index * 1_000),
                origin_charges=Decimal(0),
                destination_charges=Decimal(0),
                transit_time_days=20,
                quote_valid_until=(NOW + timedelta(days=30)).date(),
            )
            barrier.wait()
            submit_bid(session, clock, rfq_id, supplier, data)
            session.commit()

    with ThreadPoolExecutor(len(supplier_ids)) as pool:
        list(pool.map(place, enumerate(supplier_ids)))  # list() re-raises worker exceptions


def test_simultaneous_bids_extend_one_after_another(session_factory, clock):
    # Window of 30 min means every bid is inside it, whatever the close has moved to.
    rfq_id, suppliers = setup_auction(session_factory, clock, window=30, forced_after=12)
    clock.set(CLOSE - timedelta(minutes=1))

    bid_simultaneously(session_factory, clock, rfq_id, suppliers)

    with session_factory() as session:
        rfq = session.get(Rfq, rfq_id)
        events = session.scalars(
            select(AuctionEvent).where(AuctionEvent.rfq_id == rfq_id).order_by(AuctionEvent.id)
        ).all()

    counts = Counter(e.event_type for e in events)
    # 13:00 -> 13:05 -> 13:10 -> 13:12 (capped), then every later bid is blocked.
    assert rfq.current_close_at == CLOSE + timedelta(minutes=12)
    assert rfq.extension_count == 3
    assert counts[EventType.BID_SUBMITTED] == SUPPLIERS
    assert counts[EventType.EXTENDED] == 3
    assert counts[EventType.EXTENSION_SKIPPED] == SUPPLIERS - 3

    # Each extension starts exactly where the previous one ended: no lost updates.
    extensions = [e for e in events if e.event_type is EventType.EXTENDED]
    for previous, current in zip(extensions, extensions[1:]):
        assert current.previous_close_at == previous.new_close_at


def test_simultaneous_bids_record_consistent_ranks(session_factory, clock):
    rfq_id, suppliers = setup_auction(session_factory, clock, window=10, forced_after=20)
    clock.set(NOW + timedelta(minutes=5))

    bid_simultaneously(session_factory, clock, rfq_id, suppliers)

    # Replaying the bids in the order they took the lock must reproduce the rank
    # each one was told. Two bids ranked against the same stale snapshot would not.
    with session_factory() as session:
        bids = session.scalars(select(Bid).where(Bid.rfq_id == rfq_id).order_by(Bid.id)).all()
        recorded = {
            e.bid_id: e.details["rank"]
            for e in session.scalars(
                select(AuctionEvent).where(AuctionEvent.event_type == EventType.BID_SUBMITTED)
            )
        }
    ranking: list[Standing] = []
    for bid in bids:
        change = apply_bid(ranking, Standing(bid.supplier_id, bid.total_amount, bid.created_at, bid.id))
        assert recorded[bid.id] == change.new_position + 1
        ranking = change.after
