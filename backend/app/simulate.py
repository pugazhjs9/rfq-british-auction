"""Demo bot that keeps bidding on one auction so you can watch extensions happen.

Run with: python -m app.simulate RFQ_ID [--every SECONDS]
"""

import argparse
import random
import time
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.clock import DbClock
from app.db import SessionLocal
from app.engine import AuctionStatus
from app.errors import AppError
from app.models import Rfq, User, UserRole
from app.realtime import publisher
from app.schemas import BidCreate
from app.services.bids import submit_bid
from app.services.standings import current_ranking

CARRIERS = ["Maersk", "MSC", "Hapag-Lloyd", "CMA CGM", "ONE", "Evergreen"]


def next_quote(rfq: Rfq, own_total: Decimal | None, l1_total: Decimal | None) -> BidCreate:
    """Undercut L1 most of the time; otherwise just improve on our own price."""
    reference = l1_total if l1_total and random.random() < 0.7 else own_total or l1_total
    total = (reference or Decimal(100_000)) * Decimal(1 - random.uniform(0.004, 0.02))
    if own_total is not None:
        total = min(total, own_total - 1)
    total = total.quantize(Decimal("1"))
    origin, destination = (total * Decimal("0.06")).quantize(Decimal("1")), (total * Decimal("0.09")).quantize(Decimal("1"))
    return BidCreate(
        carrier_name=random.choice(CARRIERS),
        freight_charges=total - origin - destination,
        origin_charges=origin,
        destination_charges=destination,
        transit_time_days=random.randint(4, 30),
        quote_valid_until=rfq.pickup_date + timedelta(days=14),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rfq_id", type=int)
    parser.add_argument("--every", type=float, default=8.0, help="average seconds between bids")
    args = parser.parse_args()
    clock = DbClock()

    while True:
        with SessionLocal() as session:
            rfq = session.get(Rfq, args.rfq_id)
            if rfq is None:
                raise SystemExit(f"No RFQ with id {args.rfq_id}")
            status = rfq.status_at(clock.now(session))
            if status in (AuctionStatus.CLOSED, AuctionStatus.FORCE_CLOSED):
                print(f"{rfq.reference_id} is {status.value.lower().replace('_', ' ')}. Done.")
                return
            if status is AuctionStatus.ACTIVE:
                suppliers = session.scalars(select(User).where(User.role == UserRole.SUPPLIER)).all()
                supplier = random.choice(suppliers)
                ranking, standing = current_ranking(session, rfq.id)
                own = standing.get(supplier.id)
                l1_total = ranking[0].total if ranking else None
                data = next_quote(rfq, own.total_amount if own else None, l1_total)
                try:
                    outcome = submit_bid(session, clock, rfq.id, supplier, data)
                    session.commit()
                    publisher.publish(rfq.id, [e.event_type.value for e in outcome.events], rfq.current_close_at)
                    for event in outcome.events:
                        print(event.message)
                except AppError as error:
                    session.rollback()
                    print(f"{supplier.company}: {error.message}")
        time.sleep(random.uniform(0.5, 1.5) * args.every)


if __name__ == "__main__":
    main()
