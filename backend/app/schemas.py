from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.engine import AuctionStatus, TriggerType
from app.models import EventType, UserRole

Money = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"), max_digits=12, decimal_places=2)]


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #


class RfqCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=200)
    # Off gives a fixed close: leave out the forced close and the extension settings.
    british_auction: bool = True
    # Times must carry a UTC offset; a bare "18:00" is ambiguous across time zones.
    bid_start_at: AwareDatetime
    bid_close_at: AwareDatetime
    forced_close_at: AwareDatetime | None = Field(default=None, validate_default=True)
    pickup_date: date
    trigger_window_minutes: int | None = Field(default=None, ge=1, le=240, validate_default=True)
    extension_minutes: int | None = Field(default=None, ge=1, le=240, validate_default=True)
    trigger_type: TriggerType | None = Field(default=None, validate_default=True)

    # Field validators run in declaration order, so each one can see the
    # fields declared above it through `info.data`.
    @field_validator("forced_close_at", "trigger_window_minutes", "extension_minutes", "trigger_type")
    @classmethod
    def _british_auction_settings(cls, value: Any, info: ValidationInfo) -> Any:
        british = info.data.get("british_auction", True)
        if british and value is None:
            raise ValueError("Required for a British auction")
        if not british and value is not None:
            raise ValueError("Only British auctions have this setting")
        return value

    @field_validator("bid_close_at")
    @classmethod
    def _close_after_start(cls, value: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("bid_start_at")
        if start is not None and value <= start:
            raise ValueError("Bid close time must be after the bid start time")
        return value

    @field_validator("forced_close_at")
    @classmethod
    def _forced_after_close(cls, value: datetime | None, info: ValidationInfo) -> datetime | None:
        close = info.data.get("bid_close_at")
        if value is not None and close is not None and value <= close:
            raise ValueError("Forced close time must be later than the bid close time")
        return value

    @field_validator("pickup_date")
    @classmethod
    def _pickup_after_auction(cls, value: date, info: ValidationInfo) -> date:
        british = info.data.get("british_auction", True)
        last_close = info.data.get("forced_close_at" if british else "bid_close_at")
        if last_close is not None and value < last_close.date():
            what = "forced close" if british else "close"
            raise ValueError(f"Pickup date can't be before the auction's {what} date")
        return value


class BidCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    carrier_name: str = Field(min_length=1, max_length=120)
    freight_charges: Money
    origin_charges: Money
    destination_charges: Money
    transit_time_days: int = Field(ge=1, le=365)
    quote_valid_until: date


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    company: str
    role: UserRole


class BidOut(BaseModel):
    id: int
    # Suppliers don't see who their competitors are (app/visibility.py). For a
    # hidden supplier, `supplier` and `carrier_name` are None and `bidder` is an
    # alias such as "Supplier B". Otherwise `bidder` is the company name.
    supplier: UserOut | None
    bidder: str
    carrier_name: str | None
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total_amount: Decimal
    transit_time_days: int
    quote_valid_until: date
    created_at: datetime
    # Rank of this bid if it is the supplier's current one; None for superseded bids.
    rank: int | None = None


class RankedBidOut(BidOut):
    rank: int
    revisions: int  # how many bids this supplier has placed


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType
    message: str
    actor: UserOut | None
    bid_id: int | None
    previous_close_at: datetime | None
    new_close_at: datetime | None
    details: dict[str, Any]
    created_at: datetime


class RfqSummaryOut(BaseModel):
    id: int
    reference_id: str
    name: str
    status: AuctionStatus
    british_auction: bool
    bid_start_at: datetime
    bid_close_at: datetime
    current_close_at: datetime
    # These four are None when the RFQ isn't a British auction.
    forced_close_at: datetime | None
    trigger_window_minutes: int | None
    extension_minutes: int | None
    trigger_type: TriggerType | None
    extension_count: int
    lowest_bid: Decimal | None
    # None when there are no bids, or when the viewer may not see who is L1.
    l1_supplier: str | None
    bid_count: int
    supplier_count: int
    # The lowest of each supplier's first quote: what the buyer would pay if
    # everyone had quoted once. Savings = best_first_quote - lowest_bid.
    best_first_quote: Decimal | None
    # The viewing supplier's own rank, if it has bid.
    my_rank: int | None


class RfqDetailOut(RfqSummaryOut):
    pickup_date: date
    buyer: UserOut
    ranking: list[RankedBidOut]
    bids: list[BidOut]
    events: list[EventOut]
    server_time: datetime


class BidResultOut(BaseModel):
    bid: BidOut
    rank: int
    previous_rank: int | None
    extended: bool
    current_close_at: datetime


class ServerTimeOut(BaseModel):
    now: datetime
