import enum
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    Sequence,
    String,
    Text,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.engine import AuctionStatus, ExtensionRules, TriggerType, auction_status

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UserRole(str, enum.Enum):
    BUYER = "BUYER"
    SUPPLIER = "SUPPLIER"


class EventType(str, enum.Enum):
    AUCTION_CREATED = "AUCTION_CREATED"
    BID_SUBMITTED = "BID_SUBMITTED"
    EXTENDED = "EXTENDED"
    EXTENSION_SKIPPED = "EXTENSION_SKIPPED"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    AUCTION_FORCE_CLOSED = "AUCTION_FORCE_CLOSED"


Timestamp = DateTime(timezone=True)
Money = Numeric(12, 2)

# Human-friendly RFQ references (RFQ-00001) come from their own sequence so the
# database hands them out atomically.
rfq_reference_seq = Sequence("rfq_reference_seq", metadata=Base.metadata)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Rfq(Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        CheckConstraint("bid_start_at < bid_close_at", name="bid_close_after_start"),
        CheckConstraint("bid_close_at < forced_close_at", name="forced_close_after_bid_close"),
        # A British auction has all of its extension settings; any other RFQ has none.
        CheckConstraint(
            "(british_auction AND forced_close_at IS NOT NULL AND trigger_window_minutes IS NOT NULL"
            " AND extension_minutes IS NOT NULL AND trigger_type IS NOT NULL)"
            " OR (NOT british_auction AND forced_close_at IS NULL AND trigger_window_minutes IS NULL"
            " AND extension_minutes IS NULL AND trigger_type IS NULL)",
            name="british_auction_settings",
        ),
        # Last line of defence for "an auction never extends past its forced close".
        # Without a forced close (no British auction) the close can't move at all.
        CheckConstraint(
            "current_close_at >= bid_close_at"
            " AND current_close_at <= COALESCE(forced_close_at, bid_close_at)",
            name="current_close_within_bounds",
        ),
        CheckConstraint("trigger_window_minutes > 0", name="trigger_window_positive"),
        CheckConstraint("extension_minutes > 0", name="extension_positive"),
        # The close job only scans auctions it hasn't finalized yet.
        Index(
            "ix_rfqs_unfinalized_close",
            "current_close_at",
            postgresql_where=text("finalized_at IS NULL"),
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'RFQ-' || lpad(nextval('rfq_reference_seq')::text, 5, '0')"),
    )
    name: Mapped[str] = mapped_column(String(200))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pickup_date: Mapped[date]
    bid_start_at: Mapped[datetime] = mapped_column(Timestamp)
    bid_close_at: Mapped[datetime] = mapped_column(Timestamp)  # as scheduled; never changes
    current_close_at: Mapped[datetime] = mapped_column(Timestamp)  # moves with extensions
    # Off means a fixed close: no forced close, no extension settings.
    british_auction: Mapped[bool] = mapped_column(default=True, server_default=true())
    forced_close_at: Mapped[datetime | None] = mapped_column(Timestamp)
    trigger_window_minutes: Mapped[int | None]
    extension_minutes: Mapped[int | None]
    trigger_type: Mapped[TriggerType | None] = mapped_column(Enum(TriggerType, name="trigger_type"))
    extension_count: Mapped[int] = mapped_column(default=0, server_default="0")
    # Set by the close job once the closing event has been written.
    finalized_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())

    buyer: Mapped[User] = relationship()

    @property
    def rules(self) -> ExtensionRules | None:
        if not self.british_auction:
            return None
        return ExtensionRules(
            trigger_window=timedelta(minutes=self.trigger_window_minutes),
            extension=timedelta(minutes=self.extension_minutes),
            trigger=self.trigger_type,
        )

    def status_at(self, now: datetime) -> AuctionStatus:
        return auction_status(now, self.bid_start_at, self.current_close_at, self.forced_close_at)


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint("freight_charges >= 0", name="freight_non_negative"),
        CheckConstraint("origin_charges >= 0", name="origin_non_negative"),
        CheckConstraint("destination_charges >= 0", name="destination_non_negative"),
        CheckConstraint("transit_time_days > 0", name="transit_time_positive"),
        # Latest bid per supplier (DISTINCT ON) when building the ranking.
        Index("ix_bids_rfq_supplier_latest", "rfq_id", "supplier_id", text("created_at DESC")),
        # Lowest bid per RFQ for the listing page.
        Index("ix_bids_rfq_total", "rfq_id", "total_amount"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    carrier_name: Mapped[str] = mapped_column(String(120))
    freight_charges: Mapped[Decimal] = mapped_column(Money)
    origin_charges: Mapped[Decimal] = mapped_column(Money)
    destination_charges: Mapped[Decimal] = mapped_column(Money)
    # The database owns the total, so it can never disagree with its parts.
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        Computed("freight_charges + origin_charges + destination_charges", persisted=True),
    )
    transit_time_days: Mapped[int]
    quote_valid_until: Mapped[date]
    # Set from the auction clock, not a server default, so it matches the time
    # the extension rules were evaluated against.
    created_at: Mapped[datetime] = mapped_column(Timestamp)

    supplier: Mapped[User] = relationship()


class AuctionEvent(Base):
    """Append-only activity log: bids, extensions (with their reason) and closes."""

    __tablename__ = "auction_events"
    __table_args__ = (Index("ix_auction_events_rfq_time", "rfq_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"))
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="auction_event_type"))
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    previous_close_at: Mapped[datetime | None] = mapped_column(Timestamp)
    new_close_at: Mapped[datetime | None] = mapped_column(Timestamp)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(Timestamp)

    actor: Mapped[User | None] = relationship()
