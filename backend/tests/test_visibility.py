"""Unit tests for supplier aliases and per-viewer messages. No database needed."""

import pytest

from app.messages import render
from app.models import AuctionEvent, EventType, User, UserRole
from app.visibility import View, alias, assign_aliases

KESTREL, SAFFRON, MONSOON = 11, 12, 13
COMPANIES = {KESTREL: "Kestrel", SAFFRON: "Saffron", MONSOON: "Monsoon"}
ALIASES = {KESTREL: "Supplier A", SAFFRON: "Supplier B", MONSOON: "Supplier C"}


def viewer(user_id: int, role: UserRole) -> User:
    return User(id=user_id, name="", company=COMPANIES.get(user_id, "Indigo"), role=role)


def view_of(user: User | None) -> View:
    return View.of(user, companies=COMPANIES, aliases=ALIASES)


BUYER = view_of(viewer(1, UserRole.BUYER))
AS_SAFFRON = view_of(viewer(SAFFRON, UserRole.SUPPLIER))
ANONYMOUS = view_of(None)


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, "Supplier A"),
        (25, "Supplier Z"),
        (26, "Supplier AA"),
        (27, "Supplier AB"),
        (701, "Supplier ZZ"),
        (702, "Supplier AAA"),
    ],
)
def test_alias_counts_like_spreadsheet_columns(index, expected):
    assert alias(index) == expected


def test_aliases_follow_first_bid_and_never_change():
    assert assign_aliases([SAFFRON, KESTREL, SAFFRON, MONSOON, KESTREL]) == {
        SAFFRON: "Supplier A",
        KESTREL: "Supplier B",
        MONSOON: "Supplier C",
    }


def test_who_sees_whom():
    assert [BUYER.name(s) for s in COMPANIES] == ["Kestrel", "Saffron", "Monsoon"]
    assert [AS_SAFFRON.name(s) for s in COMPANIES] == ["Supplier A", "Saffron", "Supplier C"]
    assert [ANONYMOUS.name(s) for s in COMPANIES] == ["Supplier A", "Supplier B", "Supplier C"]


def event(event_type: EventType, actor_id: int | None = None, **details) -> AuctionEvent:
    return AuctionEvent(event_type=event_type, actor_id=actor_id, details=details, message="stored")


def test_bid_message_hides_competitor_and_carrier():
    bid = event(EventType.BID_SUBMITTED, KESTREL, total="90000.00", carrier="Maersk", rank=1, previous_rank=3)
    assert render(bid, BUYER) == "Kestrel bid ₹90,000 with Maersk (now L1, up from L3)"
    assert render(bid, AS_SAFFRON) == "Supplier A bid ₹90,000 (now L1, up from L3)"
    assert render(bid, view_of(viewer(KESTREL, UserRole.SUPPLIER))) == (
        "Kestrel bid ₹90,000 with Maersk (now L1, up from L3)"
    )


def test_extension_message_names_both_suppliers_as_the_viewer_may_see_them():
    extended = event(
        EventType.EXTENDED,
        SAFFRON,
        trigger="L1_CHANGE",
        rank=1,
        previous_rank=2,
        previous_l1_id=KESTREL,
        before_close_seconds=130,
        requested_seconds=300,
        applied_seconds=240,
        capped=True,
    )
    assert render(extended, BUYER) == (
        "Extended by 4 min: Saffron took L1 from Kestrel 2 min 10 s before close."
        " Cut short of 5 min by the forced close time."
    )
    assert render(extended, AS_SAFFRON).startswith("Extended by 4 min: Saffron took L1 from Supplier A 2 min 10 s")


def test_closing_message():
    closed = event(EventType.AUCTION_CLOSED, winner_id=MONSOON, total="70900.00", suppliers=1, bids=4, extensions=None)
    assert render(closed, BUYER) == "Closed. L1: Monsoon at ₹70,900 (1 supplier, 4 bids)."
    assert render(closed, AS_SAFFRON) == "Closed. L1: Supplier C at ₹70,900 (1 supplier, 4 bids)."
    empty = event(EventType.AUCTION_FORCE_CLOSED, winner_id=None, total=None, suppliers=0, bids=0, extensions=2)
    assert render(empty, AS_SAFFRON) == "Force-closed at the forced close time with no bids (2 extensions)."


def test_events_without_supplier_names_keep_their_stored_message():
    assert render(event(EventType.AUCTION_CREATED, 1), ANONYMOUS) == "stored"
