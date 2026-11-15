"""Demo data. Run with: python -m app.seed [--reset]

Past auctions are not inserted as raw rows: their bids are replayed through the
real services with a frozen clock, so every extension and log entry is exactly
what the live system would have produced.
"""

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.clock import DbClock, FrozenClock
from app.db import SessionLocal
from app.engine import TriggerType
from app.models import Rfq, User, UserRole
from app.schemas import BidCreate, RfqCreate
from app.services.bids import submit_bid
from app.services.closing import finalize_due_auctions
from app.services.rfqs import create_rfq

BUYER = ("Ananya Rao", "Indigo Retail")
SUPPLIERS = [
    ("Arjun Mehta", "Kestrel Freight Lines", "Maersk"),
    ("Priya Nair", "Saffron Cargo", "MSC"),
    ("Rohan Das", "Monsoon Logistics", "Hapag-Lloyd"),
    ("Meera Iyer", "Northstar Forwarding", "CMA CGM"),
]
CARRIER = {company: carrier for _, company, carrier in SUPPLIERS}


def quote(supplier: User, total: int, pickup: date, transit_days: int) -> BidCreate:
    """Split a total into realistic freight / origin / destination charges."""
    origin, destination = round(total * 0.06), round(total * 0.09)
    return BidCreate(
        carrier_name=CARRIER[supplier.company],
        freight_charges=Decimal(total - origin - destination),
        origin_charges=Decimal(origin),
        destination_charges=Decimal(destination),
        transit_time_days=transit_days,
        quote_valid_until=pickup + timedelta(days=21),
    )


def replay(session, clock, buyer, start, close_after, rules, name, pickup, bids):
    """Create an RFQ at `start` and play `bids` (minute offset, supplier, total, transit days).

    `rules` is (forced close minutes after start, X, Y, trigger), or None for an
    RFQ without the British auction option.
    """
    if rules is None:
        settings = {"british_auction": False}
    else:
        forced_after, window, extension, trigger = rules
        settings = {
            "forced_close_at": start + timedelta(minutes=forced_after),
            "trigger_window_minutes": window,
            "extension_minutes": extension,
            "trigger_type": trigger,
        }
    clock.set(start - timedelta(minutes=5))
    rfq = create_rfq(
        session,
        clock,
        buyer,
        RfqCreate(
            name=name,
            bid_start_at=start,
            bid_close_at=start + timedelta(minutes=close_after),
            pickup_date=pickup,
            **settings,
        ),
    )
    for offset, supplier, total, transit in bids:
        clock.set(start + timedelta(minutes=offset))
        submit_bid(session, clock, rfq.id, supplier, quote(supplier, total, pickup, transit))
    return rfq


def seed(session: Session) -> None:
    buyer = User(name=BUYER[0], company=BUYER[1], role=UserRole.BUYER)
    suppliers = [User(name=n, company=c, role=UserRole.SUPPLIER) for n, c, _ in SUPPLIERS]
    session.add_all([buyer, *suppliers])
    session.flush()
    kestrel, saffron, monsoon, northstar = suppliers

    now = DbClock().now(session).replace(second=0, microsecond=0)
    clock = FrozenClock(now)

    # Yesterday: one late L1 change earned an extension, then it closed normally.
    start = now - timedelta(days=1, hours=2)
    replay(
        session, clock, buyer, start, 45, (75, 8, 4, TriggerType.L1_CHANGE),
        "Chennai to Singapore, LCL 12 CBM", (start + timedelta(days=4)).date(),
        [
            (4, kestrel, 96_000, 6),
            (9, saffron, 92_500, 7),
            (22, monsoon, 94_000, 5),
            (39, monsoon, 91_200, 5),     # takes L1 inside the window: 45 -> 49
            (44, kestrel, 91_800, 6),     # moves up to L2 but L1 unchanged: no extension
            (47, saffron, 91_500, 7),     # overtakes Kestrel for L2; L1 unchanged: no extension
        ],
    )

    # This morning: a bidding war ran into the forced close.
    start = now - timedelta(hours=3)
    replay(
        session, clock, buyer, start, 60, (70, 10, 5, TriggerType.BID_RECEIVED),
        "Nhava Sheva to Rotterdam, 2x40ft HC", (start + timedelta(days=6)).date(),
        [
            (5, kestrel, 182_000, 24),
            (12, saffron, 176_500, 26),
            (30, monsoon, 179_000, 23),
            (41, kestrel, 171_000, 24),
            (52, saffron, 169_500, 26),   # inside the window: 60 -> 65
            (58, northstar, 172_000, 25), # 65 -> 70, which is the forced close
            (63, kestrel, 168_000, 24),   # trigger fires but nothing left to add
            (69, monsoon, 167_200, 23),
        ],
    )

    # Live now: ranking changes in the last 5 minutes add 3 minutes.
    start = now - timedelta(minutes=40)
    replay(
        session, clock, buyer, start, 48, (60, 5, 3, TriggerType.ANY_RANK_CHANGE),
        "Mundra to Jebel Ali, 4x20ft dry", (now + timedelta(days=3)).date(),
        [
            (3, saffron, 64_000, 5),
            (9, kestrel, 61_500, 4),
            (17, northstar, 62_800, 6),
            (26, saffron, 60_900, 5),
            (34, monsoon, 63_300, 4),
        ],
    )

    # Opens in half an hour.
    start = now + timedelta(minutes=30)
    clock.set(now)
    create_rfq(
        session,
        clock,
        buyer,
        RfqCreate(
            name="Delhi ICD to Hamburg, 1x40ft reefer",
            bid_start_at=start,
            bid_close_at=start + timedelta(hours=1),
            forced_close_at=start + timedelta(hours=1, minutes=30),
            pickup_date=(now + timedelta(days=10)).date(),
            trigger_window_minutes=10,
            extension_minutes=5,
            trigger_type=TriggerType.L1_CHANGE,
        ),
    )

    # Earlier today, without the British auction option: the bid two minutes
    # before the end took L1 but didn't extend anything.
    start = now - timedelta(hours=5)
    replay(
        session, clock, buyer, start, 60, None,
        "Kolkata to Dhaka by road, 2 FTL trucks", (start + timedelta(days=3)).date(),
        [
            (6, monsoon, 74_000, 3),
            (15, northstar, 71_500, 2),
            (33, kestrel, 72_400, 3),
            (58, monsoon, 70_900, 3),     # L1 change, but the close stays put
        ],
    )

    finalize_due_auctions(session, FrozenClock(now))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="wipe all data first")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.reset:
            session.execute(text("TRUNCATE auction_events, bids, rfqs, users RESTART IDENTITY CASCADE"))
            session.execute(text("ALTER SEQUENCE rfq_reference_seq RESTART"))
        elif session.scalar(select(func.count(User.id))):
            print("Database already has data; skipping seed (use --reset to start over).")
            return
        seed(session)
        session.commit()
        print(f"Seeded {session.scalar(select(func.count(Rfq.id)))} RFQs.")


if __name__ == "__main__":
    main()
