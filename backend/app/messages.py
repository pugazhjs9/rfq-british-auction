"""Activity-log messages, written from each event's structured details.

Every viewer gets the same sentence, with suppliers named as their View
allows: "Saffron Cargo took L1 from Kestrel Freight Lines" for the buyer,
"Supplier B took L1 from Kestrel Freight Lines" for Kestrel. When an event
is written, the version with every name visible is stored in
auction_events.message as the audit copy.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.engine import TriggerType
from app.formatting import format_duration, format_inr
from app.models import AuctionEvent, EventType
from app.visibility import View


def render(event: AuctionEvent, view: View) -> str:
    details = event.details
    match event.event_type:
        case EventType.BID_SUBMITTED:
            return bid_message(event.actor_id, details, view)
        case EventType.EXTENDED | EventType.EXTENSION_SKIPPED:
            return extension_message(event.event_type, event.actor_id, details, view)
        case EventType.AUCTION_CLOSED | EventType.AUCTION_FORCE_CLOSED:
            return closing_message(event.event_type, details, view)
    return event.message  # names no supplier


def bid_message(supplier_id: int, details: dict[str, Any], view: View) -> str:
    rank, previous = details["rank"], details["previous_rank"]
    standing = f"now L{rank}"
    if previous is not None and previous != rank:
        standing += f", up from L{previous}"
    # The carrier is part of a supplier's identity, so it is hidden along with the name.
    carrier = f" with {details['carrier']}" if view.sees(supplier_id) else ""
    return f"{view.name(supplier_id)} bid {format_inr(Decimal(details['total']))}{carrier} ({standing})"


def trigger_reason(supplier_id: int, details: dict[str, Any], view: View) -> str:
    """Why the trigger fired, e.g. 'Saffron Cargo took L1 from Kestrel Freight Lines 2 min before close'."""
    bidder = view.name(supplier_id)
    timing = f"{_duration(details['before_close_seconds'])} before close"
    rank, previous = details["rank"], details["previous_rank"]
    match TriggerType(details["trigger"]):
        case TriggerType.BID_RECEIVED:
            return f"{bidder} bid {timing}"
        case TriggerType.ANY_RANK_CHANGE:
            if previous is None:
                return f"{bidder} entered the ranking at L{rank} {timing}"
            return f"{bidder} moved from L{previous} to L{rank} {timing}"
        case TriggerType.L1_CHANGE:
            previous_l1 = details["previous_l1_id"]
            if previous_l1 is None:
                return f"{bidder} became L1 with the first bid, {timing}"
            return f"{bidder} took L1 from {view.name(previous_l1)} {timing}"
    raise ValueError(f"Unknown trigger type: {details['trigger']!r}")


def extension_message(event_type: EventType, supplier_id: int, details: dict[str, Any], view: View) -> str:
    reason = trigger_reason(supplier_id, details, view)
    if event_type is EventType.EXTENSION_SKIPPED:
        return f"Not extended: {reason}, but the auction is already at its forced close time."
    message = f"Extended by {_duration(details['applied_seconds'])}: {reason}."
    if details["capped"]:
        message += f" Cut short of {_duration(details['requested_seconds'])} by the forced close time."
    return message


def closing_message(event_type: EventType, details: dict[str, Any], view: View) -> str:
    forced = event_type is EventType.AUCTION_FORCE_CLOSED
    how = "Force-closed at the forced close time" if forced else "Closed"
    winner = details["winner_id"]
    counts = []
    if winner is not None:
        counts += [_plural(details["suppliers"], "supplier"), _plural(details["bids"], "bid")]
    if details["extensions"] is not None:  # None when it isn't a British auction
        counts.append(_plural(details["extensions"], "extension"))
    tally = f" ({', '.join(counts)})" if counts else ""
    if winner is None:
        return f"{how} with no bids{tally}."
    return f"{how}. L1: {view.name(winner)} at {format_inr(Decimal(details['total']))}{tally}."


def _duration(seconds: int) -> str:
    return format_duration(timedelta(seconds=seconds))


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
