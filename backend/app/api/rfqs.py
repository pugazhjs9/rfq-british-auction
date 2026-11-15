from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, get_current_user, get_publisher, get_viewer
from app.clock import Clock
from app.db import get_session
from app.models import EventType, User
from app.realtime import Publisher
from app.schemas import BidCreate, BidResultOut, RfqCreate, RfqDetailOut, RfqSummaryOut
from app.services import queries
from app.services.bids import submit_bid
from app.services.rfqs import create_rfq
from app.visibility import View

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])


@router.get("", response_model=list[RfqSummaryOut])
def list_rfqs(
    viewer: User | None = Depends(get_viewer),
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
):
    return queries.list_auctions(session, clock.now(session), viewer)


@router.post("", response_model=RfqDetailOut, status_code=201)
def create(
    data: RfqCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
    publisher: Publisher = Depends(get_publisher),
):
    rfq = create_rfq(session, clock, user, data)
    session.commit()
    publisher.publish(rfq.id, [EventType.AUCTION_CREATED.value], rfq.current_close_at)
    return queries.auction_detail(session, rfq.id, clock.now(session), user)


@router.get("/{rfq_id}", response_model=RfqDetailOut)
def detail(
    rfq_id: int,
    viewer: User | None = Depends(get_viewer),
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
):
    return queries.auction_detail(session, rfq_id, clock.now(session), viewer)


@router.post("/{rfq_id}/bids", response_model=BidResultOut, status_code=201)
def place_bid(
    rfq_id: int,
    data: BidCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
    publisher: Publisher = Depends(get_publisher),
):
    outcome = submit_bid(session, clock, rfq_id, user, data)
    session.commit()
    # Publish only after commit, so clients that refetch see the new state.
    publisher.publish(
        rfq_id, [e.event_type.value for e in outcome.events], outcome.rfq.current_close_at
    )
    return BidResultOut(
        bid=queries.bid_out(outcome.bid, View.of(user, companies={user.id: user.company}), outcome.rank),
        rank=outcome.rank,
        previous_rank=outcome.previous_rank,
        extended=bool(outcome.extension and outcome.extension.extended),
        current_close_at=outcome.rfq.current_close_at,
    )
