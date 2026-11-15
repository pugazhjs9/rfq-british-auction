from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.engine import Standing, rank
from app.models import Bid


def load_standing_bids(session: Session, rfq_id: int) -> list[Bid]:
    """Each supplier's latest bid on an RFQ.

    Bids from one supplier must get strictly cheaper, so the latest bid is also
    their lowest. DISTINCT ON keeps one row per supplier and is served by the
    (rfq_id, supplier_id, created_at DESC) index.
    """
    return list(
        session.scalars(
            select(Bid)
            .options(joinedload(Bid.supplier))
            .where(Bid.rfq_id == rfq_id)
            .distinct(Bid.supplier_id)
            .order_by(Bid.supplier_id, Bid.created_at.desc(), Bid.id.desc())
        )
    )


def standing_of(bid: Bid) -> Standing:
    return Standing(
        supplier_id=bid.supplier_id, total=bid.total_amount, bid_at=bid.created_at, bid_id=bid.id
    )


def current_ranking(session: Session, rfq_id: int) -> tuple[list[Standing], dict[int, Bid]]:
    """The ranking (L1 first) plus each standing bid keyed by supplier id."""
    bids = load_standing_bids(session, rfq_id)
    return rank(standing_of(b) for b in bids), {b.supplier_id: b for b in bids}
