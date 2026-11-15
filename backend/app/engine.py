"""Auction rules as pure functions.

Nothing in this module touches the database or the web framework, so every
rule can be unit-tested with plain values (see tests/test_engine.py).
"""

from __future__ import annotations

import bisect
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


class TriggerType(str, enum.Enum):
    BID_RECEIVED = "BID_RECEIVED"
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
    L1_CHANGE = "L1_CHANGE"


class AuctionStatus(str, enum.Enum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


def auction_status(
    now: datetime,
    bid_start_at: datetime,
    current_close_at: datetime,
    forced_close_at: datetime | None,
) -> AuctionStatus:
    """Derive status from the clock instead of storing it, so it can never go stale.

    Bidding is open on the half-open interval [bid_start_at, current_close_at).
    An auction that ended exactly at its forced close time was force-closed:
    extensions pushed it as far as it was allowed to go. An RFQ without the
    British auction option has no forced close, so it can only end CLOSED.
    """
    if now < bid_start_at:
        return AuctionStatus.UPCOMING
    if now < current_close_at:
        return AuctionStatus.ACTIVE
    if forced_close_at is not None and current_close_at >= forced_close_at:
        return AuctionStatus.FORCE_CLOSED
    return AuctionStatus.CLOSED


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Standing:
    """A supplier's current bid, i.e. their lowest one."""

    supplier_id: int
    total: Decimal
    bid_at: datetime
    bid_id: int

    @property
    def sort_key(self) -> tuple[Decimal, datetime, int]:
        # Cheapest first. On a tie, whoever reached that price first ranks higher.
        return (self.total, self.bid_at, self.bid_id)


def rank(standings: Iterable[Standing]) -> list[Standing]:
    """Index 0 is L1, index 1 is L2, and so on."""
    return sorted(standings, key=lambda s: s.sort_key)


@dataclass(frozen=True)
class RankingChange:
    before: list[Standing]
    after: list[Standing]
    old_position: int | None  # 0-based; None when this is the supplier's first bid
    new_position: int

    @property
    def bidder_id(self) -> int:
        return self.after[self.new_position].supplier_id

    @property
    def rank_changed(self) -> bool:
        """True if any supplier's rank differs between `before` and `after`.

        Only the bidder's price moved, so every other supplier keeps their
        relative order. The full order is therefore unchanged exactly when the
        bidder already had a rank and landed back in the same slot. A first bid
        always counts: that supplier goes from unranked to ranked.
        """
        return self.old_position != self.new_position

    @property
    def previous_l1(self) -> Standing | None:
        return self.before[0] if self.before else None

    @property
    def l1_changed(self) -> bool:
        previous = self.previous_l1
        return previous is None or previous.supplier_id != self.after[0].supplier_id


def apply_bid(ranking: list[Standing], bid: Standing) -> RankingChange:
    """Move the bidder into their new slot in an already-sorted ranking.

    Binary search finds the slot in O(log n) comparisons. Copying the list
    keeps the call O(n) overall, which is no worse than loading the ranking
    from the database in the first place.
    """
    old_position = next(
        (i for i, s in enumerate(ranking) if s.supplier_id == bid.supplier_id), None
    )
    others = ranking if old_position is None else ranking[:old_position] + ranking[old_position + 1 :]
    new_position = bisect.bisect_left(others, bid.sort_key, key=lambda s: s.sort_key)
    after = [*others[:new_position], bid, *others[new_position:]]
    return RankingChange(
        before=list(ranking), after=after, old_position=old_position, new_position=new_position
    )


# --------------------------------------------------------------------------- #
# Extensions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExtensionRules:
    trigger_window: timedelta  # X
    extension: timedelta  # Y
    trigger: TriggerType


@dataclass(frozen=True)
class Extension:
    previous_close_at: datetime
    new_close_at: datetime
    capped: bool  # the forced close time cut this extension short

    @property
    def applied(self) -> timedelta:
        return self.new_close_at - self.previous_close_at

    @property
    def extended(self) -> bool:
        return self.new_close_at > self.previous_close_at


def in_trigger_window(now: datetime, current_close_at: datetime, window: timedelta) -> bool:
    """The window trails the *current* close time, so it moves with every extension."""
    return current_close_at - window <= now < current_close_at


def trigger_fired(trigger: TriggerType, change: RankingChange) -> bool:
    # The three triggers are nested: every L1 change is a rank change, and every
    # rank change comes from a bid. The setting is a strictness dial.
    match trigger:
        case TriggerType.BID_RECEIVED:
            return True
        case TriggerType.ANY_RANK_CHANGE:
            return change.rank_changed
        case TriggerType.L1_CHANGE:
            return change.l1_changed
    raise ValueError(f"Unknown trigger type: {trigger!r}")


def decide_extension(
    now: datetime,
    current_close_at: datetime,
    forced_close_at: datetime,
    rules: ExtensionRules,
    change: RankingChange,
) -> Extension | None:
    """Return the extension a bid earns, or None if it doesn't trigger one.

    The close moves to min(current close + Y, forced close). If the trigger
    fires while the auction already sits at its forced close time, the result
    has `extended == False` so the caller can log why nothing moved.
    """
    if not in_trigger_window(now, current_close_at, rules.trigger_window):
        return None
    if not trigger_fired(rules.trigger, change):
        return None
    wanted = current_close_at + rules.extension
    return Extension(
        previous_close_at=current_close_at,
        new_close_at=min(wanted, forced_close_at),
        capped=wanted > forced_close_at,
    )
