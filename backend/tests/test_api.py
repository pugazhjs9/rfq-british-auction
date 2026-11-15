"""End-to-end API tests against Postgres, with a frozen clock."""

from datetime import timedelta

import pytest

from app.services.closing import finalize_due_auctions
from tests.conftest import NOW

START = NOW
CLOSE = NOW + timedelta(hours=1)
FORCED = CLOSE + timedelta(minutes=20)


def iso(moment) -> str:
    """ISO 8601 the way the API writes it (UTC as 'Z')."""
    return moment.isoformat().replace("+00:00", "Z")


def as_user(user) -> dict[str, str]:
    return {"X-User-Id": str(user.id)}


def rfq_payload(**overrides) -> dict:
    payload = {
        "name": "Mumbai to Hamburg, 2x40ft",
        "bid_start_at": iso(START),
        "bid_close_at": iso(CLOSE),
        "forced_close_at": iso(FORCED),
        "pickup_date": (NOW + timedelta(days=5)).date().isoformat(),
        "trigger_window_minutes": 10,
        "extension_minutes": 5,
        "trigger_type": "BID_RECEIVED",
    }
    return payload | overrides


def create_rfq(client, users, **overrides) -> dict:
    response = client.post("/api/rfqs", json=rfq_payload(**overrides), headers=as_user(users["buyer"]))
    assert response.status_code == 201, response.json()
    return response.json()


def place_bid(client, rfq, supplier, total: int, **overrides):
    payload = {
        "carrier_name": "Maersk",
        "freight_charges": str(total - 1500),
        "origin_charges": "1000",
        "destination_charges": "500",
        "transit_time_days": 21,
        "quote_valid_until": (NOW + timedelta(days=30)).date().isoformat(),
    } | overrides
    return client.post(f"/api/rfqs/{rfq['id']}/bids", json=payload, headers=as_user(supplier))


def detail(client, rfq, viewer=None) -> dict:
    headers = as_user(viewer) if viewer else {}
    return client.get(f"/api/rfqs/{rfq['id']}", headers=headers).json()


def ranking(client, rfq, viewer) -> list[tuple[int, str]]:
    return [(row["rank"], row["bidder"]) for row in detail(client, rfq, viewer)["ranking"]]


def fixed_close_payload(**overrides) -> dict:
    payload = rfq_payload(british_auction=False, **overrides)
    for key in ("forced_close_at", "trigger_window_minutes", "extension_minutes", "trigger_type"):
        payload.pop(key)
    return payload


# --------------------------------------------------------------------------- #
# RFQ creation
# --------------------------------------------------------------------------- #


def test_create_rfq(client, users):
    rfq = create_rfq(client, users)
    assert rfq["reference_id"] == "RFQ-00001"
    assert rfq["status"] == "ACTIVE"
    assert rfq["current_close_at"] == rfq["bid_close_at"]
    assert rfq["events"][0]["event_type"] == "AUCTION_CREATED"
    assert "last 10 min extends the close by 5 min" in rfq["events"][0]["message"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"forced_close_at": iso(CLOSE)}, "forced_close_at"),  # must be strictly later
        ({"forced_close_at": iso(CLOSE - timedelta(minutes=1))}, "forced_close_at"),
        ({"bid_close_at": iso(START)}, "bid_close_at"),
        (
            {
                "bid_start_at": iso(NOW - timedelta(hours=2)),
                "bid_close_at": iso(NOW - timedelta(minutes=1)),
                "forced_close_at": iso(NOW + timedelta(minutes=10)),
            },
            "bid_close_at",  # already in the past
        ),
        ({"bid_start_at": "2026-01-15T12:00:00"}, "bid_start_at"),  # no time zone
        ({"pickup_date": (NOW - timedelta(days=1)).date().isoformat()}, "pickup_date"),
        ({"trigger_window_minutes": 0}, "trigger_window_minutes"),
        ({"trigger_type": "WHENEVER"}, "trigger_type"),
        ({"forced_close_at": None}, "forced_close_at"),  # British auctions need all their settings
        ({"british_auction": False}, "trigger_window_minutes"),  # a fixed close has none
    ],
)
def test_create_rfq_validation(client, users, overrides, field):
    response = client.post("/api/rfqs", json=rfq_payload(**overrides), headers=as_user(users["buyer"]))
    assert response.status_code == 422
    assert field in response.json()["errors"]


def test_create_rfq_without_british_auction(client, users):
    response = client.post("/api/rfqs", json=fixed_close_payload(), headers=as_user(users["buyer"]))
    assert response.status_code == 201, response.json()
    rfq = response.json()
    assert rfq["british_auction"] is False
    assert (rfq["forced_close_at"], rfq["trigger_type"], rfq["extension_minutes"]) == (None, None, None)
    assert "Fixed close" in rfq["events"][0]["message"]


def test_only_buyers_create_rfqs(client, users):
    response = client.post("/api/rfqs", json=rfq_payload(), headers=as_user(users["kestrel"]))
    assert response.status_code == 403


def test_writes_need_a_user(client, users):
    assert client.post("/api/rfqs", json=rfq_payload()).status_code == 401


# --------------------------------------------------------------------------- #
# Bidding and ranking
# --------------------------------------------------------------------------- #


def test_bids_rank_by_total_then_time(client, users, clock):
    rfq = create_rfq(client, users)
    place_bid(client, rfq, users["kestrel"], 500_000)
    clock.advance(minutes=1)
    place_bid(client, rfq, users["saffron"], 450_000)
    clock.advance(minutes=1)
    response = place_bid(client, rfq, users["monsoon"], 450_000)  # same price, later
    assert response.json()["rank"] == 2

    assert ranking(client, rfq, users["buyer"]) == [(1, "Saffron"), (2, "Monsoon"), (3, "Kestrel")]
    body = detail(client, rfq, users["buyer"])
    assert body["lowest_bid"] == "450000.00"
    assert body["l1_supplier"] == "Saffron"
    assert body["ranking"][0]["freight_charges"] == "448500.00"


def test_revised_bid_must_beat_own_previous_bid(client, users, clock):
    rfq = create_rfq(client, users)
    place_bid(client, rfq, users["kestrel"], 500_000)
    clock.advance(minutes=1)

    same = place_bid(client, rfq, users["kestrel"], 500_000)
    assert same.status_code == 409
    assert same.json()["code"] == "BID_NOT_LOWER"

    lower = place_bid(client, rfq, users["kestrel"], 499_999)
    assert lower.status_code == 201
    assert (lower.json()["rank"], lower.json()["previous_rank"]) == (1, 1)

    body = detail(client, rfq)
    assert body["ranking"][0]["revisions"] == 2
    assert sorted(b["rank"] is None for b in body["bids"]) == [False, True]  # old bid is superseded


def test_bidding_window_is_start_inclusive_close_exclusive(client, users, clock):
    later = START + timedelta(minutes=10)
    rfq = create_rfq(client, users, bid_start_at=iso(later))
    assert rfq["status"] == "UPCOMING"
    assert place_bid(client, rfq, users["kestrel"], 500_000).json()["code"] == "AUCTION_NOT_STARTED"

    clock.set(later)
    assert place_bid(client, rfq, users["kestrel"], 500_000).status_code == 201

    clock.set(CLOSE)
    assert place_bid(client, rfq, users["saffron"], 400_000).json()["code"] == "AUCTION_CLOSED"


def test_buyers_cannot_bid(client, users):
    rfq = create_rfq(client, users)
    assert place_bid(client, rfq, users["buyer"], 500_000).status_code == 403


def test_quote_must_be_valid_until_pickup(client, users):
    rfq = create_rfq(client, users)
    response = place_bid(client, rfq, users["kestrel"], 500_000, quote_valid_until=NOW.date().isoformat())
    assert response.status_code == 422
    assert "quote_valid_until" in response.json()["errors"]


def test_negative_charges_are_rejected(client, users):
    rfq = create_rfq(client, users)
    response = place_bid(client, rfq, users["kestrel"], 500_000, origin_charges="-1")
    assert response.status_code == 422
    assert "origin_charges" in response.json()["errors"]


# --------------------------------------------------------------------------- #
# Extensions
# --------------------------------------------------------------------------- #


def test_bid_in_window_extends_and_logs_reason(client, users, clock, publisher):
    rfq = create_rfq(client, users)

    clock.set(CLOSE - timedelta(minutes=15))
    assert place_bid(client, rfq, users["kestrel"], 500_000).json()["extended"] is False

    clock.set(CLOSE - timedelta(minutes=4))
    response = place_bid(client, rfq, users["saffron"], 490_000).json()
    assert response["extended"] is True
    assert response["current_close_at"] == iso(CLOSE + timedelta(minutes=5))

    body = detail(client, rfq, users["buyer"])
    assert body["extension_count"] == 1
    latest = body["events"][0]
    assert latest["event_type"] == "EXTENDED"
    assert (latest["previous_close_at"], latest["new_close_at"]) == (
        iso(CLOSE),
        iso(CLOSE + timedelta(minutes=5)),
    )
    assert latest["message"] == "Extended by 5 min: Saffron bid 4 min before close."
    # The live update goes out after commit and carries the new close time.
    assert publisher.messages[-1] == (
        rfq["id"],
        ["BID_SUBMITTED", "EXTENDED"],
        CLOSE + timedelta(minutes=5),
    )


def test_rank_change_trigger(client, users, clock):
    rfq = create_rfq(client, users, trigger_type="ANY_RANK_CHANGE")
    place_bid(client, rfq, users["kestrel"], 400_000)
    place_bid(client, rfq, users["saffron"], 450_000)

    clock.set(CLOSE - timedelta(minutes=3))
    assert place_bid(client, rfq, users["saffron"], 420_000).json()["extended"] is False
    assert place_bid(client, rfq, users["saffron"], 390_000).json()["extended"] is True
    assert "Saffron moved from L2 to L1" in detail(client, rfq, users["buyer"])["events"][0]["message"]


def test_l1_change_trigger(client, users, clock):
    rfq = create_rfq(client, users, trigger_type="L1_CHANGE")
    place_bid(client, rfq, users["kestrel"], 400_000)
    place_bid(client, rfq, users["saffron"], 450_000)
    place_bid(client, rfq, users["monsoon"], 500_000)

    clock.set(CLOSE - timedelta(minutes=3))
    assert place_bid(client, rfq, users["monsoon"], 420_000).json()["extended"] is False  # L3 -> L2
    assert place_bid(client, rfq, users["kestrel"], 380_000).json()["extended"] is False  # L1 stays L1
    assert place_bid(client, rfq, users["saffron"], 370_000).json()["extended"] is True
    assert "Saffron took L1 from Kestrel" in detail(client, rfq, users["buyer"])["events"][0]["message"]


def test_extensions_stop_at_forced_close(client, users, clock, session_factory):
    forced = CLOSE + timedelta(minutes=8)
    rfq = create_rfq(client, users, forced_close_at=iso(forced))

    clock.set(CLOSE - timedelta(minutes=1))
    assert place_bid(client, rfq, users["kestrel"], 500_000).json()["current_close_at"] == iso(
        CLOSE + timedelta(minutes=5)
    )

    clock.set(CLOSE + timedelta(minutes=3))
    capped = place_bid(client, rfq, users["saffron"], 490_000).json()
    assert capped["current_close_at"] == iso(forced)  # wanted +5, only 4 min were left
    assert "Cut short of 5 min" in detail(client, rfq)["events"][0]["message"]

    clock.set(forced - timedelta(minutes=1))
    blocked = place_bid(client, rfq, users["monsoon"], 480_000).json()
    assert blocked["extended"] is False
    assert detail(client, rfq)["events"][0]["event_type"] == "EXTENSION_SKIPPED"

    clock.set(forced)
    assert place_bid(client, rfq, users["northstar"], 470_000).json()["code"] == "AUCTION_CLOSED"
    assert detail(client, rfq)["status"] == "FORCE_CLOSED"


def test_without_british_auction_late_bids_never_extend(client, users, clock, session_factory):
    rfq = client.post("/api/rfqs", json=fixed_close_payload(), headers=as_user(users["buyer"])).json()
    place_bid(client, rfq, users["kestrel"], 500_000)

    clock.set(CLOSE - timedelta(seconds=30))
    late = place_bid(client, rfq, users["saffron"], 400_000).json()  # takes L1 at the last moment
    assert (late["rank"], late["extended"], late["current_close_at"]) == (1, False, iso(CLOSE))

    clock.set(CLOSE)
    assert place_bid(client, rfq, users["monsoon"], 300_000).json()["code"] == "AUCTION_CLOSED"
    with session_factory() as session:
        finalize_due_auctions(session, clock)
        session.commit()
    body = detail(client, rfq, users["buyer"])
    assert body["status"] == "CLOSED"
    assert [e["event_type"] for e in body["events"]] == [
        "AUCTION_CLOSED",
        "BID_SUBMITTED",
        "BID_SUBMITTED",
        "AUCTION_CREATED",
    ]
    assert body["events"][0]["message"] == "Closed. L1: Saffron at ₹4,00,000 (2 suppliers, 2 bids)."


# --------------------------------------------------------------------------- #
# Who sees what
# --------------------------------------------------------------------------- #


def test_suppliers_see_competitors_only_as_aliases(client, users, clock):
    rfq = create_rfq(client, users, trigger_type="L1_CHANGE")
    place_bid(client, rfq, users["kestrel"], 500_000)
    clock.advance(minutes=1)
    place_bid(client, rfq, users["saffron"], 480_000)
    clock.set(CLOSE - timedelta(minutes=2))
    place_bid(client, rfq, users["kestrel"], 470_000, carrier_name="Hapag-Lloyd")  # takes L1 back

    buyer = detail(client, rfq, users["buyer"])
    assert [(r["bidder"], r["carrier_name"]) for r in buyer["ranking"]] == [
        ("Kestrel", "Hapag-Lloyd"),
        ("Saffron", "Maersk"),
    ]
    assert buyer["events"][0]["message"].startswith("Extended by 5 min: Kestrel took L1 from Saffron")

    saffron = detail(client, rfq, users["saffron"])
    assert [(r["rank"], r["bidder"], r["supplier"], r["carrier_name"]) for r in saffron["ranking"]] == [
        (1, "Supplier A", None, None),  # aliases follow the order of first bids
        (2, "Saffron", buyer["ranking"][1]["supplier"], "Maersk"),
    ]
    assert {b["bidder"] for b in saffron["bids"]} == {"Supplier A", "Saffron"}
    assert (saffron["l1_supplier"], saffron["my_rank"], saffron["lowest_bid"]) == (None, 2, "470000.00")
    latest = saffron["events"][0]
    assert latest["message"].startswith("Extended by 5 min: Supplier A took L1 from Saffron")
    assert (latest["actor"], latest["details"]) == (None, {})
    assert saffron["events"][-1]["actor"]["company"] == "Indigo Retail"  # the buyer isn't hidden

    sent = str(saffron)
    assert "Kestrel" not in sent and "Hapag-Lloyd" not in sent
    assert all(e["actor"] is None or e["actor"]["id"] != users["kestrel"].id for e in saffron["events"])

    kestrel = detail(client, rfq, users["kestrel"])
    assert (kestrel["l1_supplier"], kestrel["my_rank"]) == ("Kestrel", 1)

    anonymous = detail(client, rfq)
    assert [r["bidder"] for r in anonymous["ranking"]] == ["Supplier A", "Supplier B"]
    assert "Saffron" not in str(anonymous["events"]) and "Kestrel" not in str(anonymous["events"])


def test_listing_shows_suppliers_their_own_rank(client, users, clock):
    rfq = create_rfq(client, users)
    place_bid(client, rfq, users["kestrel"], 500_000)
    place_bid(client, rfq, users["saffron"], 490_000)
    place_bid(client, rfq, users["kestrel"], 470_000)
    create_rfq(client, users, name="No bids from Saffron")

    def listing(viewer):
        rows = client.get("/api/rfqs", headers=as_user(viewer)).json()
        return {r["id"]: (r["l1_supplier"], r["my_rank"], r["best_first_quote"]) for r in rows}

    assert listing(users["buyer"]) == {1: ("Kestrel", None, "490000.00"), 2: (None, None, None)}
    assert listing(users["saffron"]) == {1: (None, 2, "490000.00"), 2: (None, None, None)}
    assert listing(users["kestrel"])[1] == ("Kestrel", 1, "490000.00")


# --------------------------------------------------------------------------- #
# Closing
# --------------------------------------------------------------------------- #


def test_close_job_writes_one_closing_event(client, users, clock, session_factory):
    rfq = create_rfq(client, users)
    place_bid(client, rfq, users["kestrel"], 500_000)
    place_bid(client, rfq, users["saffron"], 480_000)

    clock.set(CLOSE)
    assert detail(client, rfq)["status"] == "CLOSED"  # status doesn't wait for the job

    for expected in ([(rfq["id"], "AUCTION_CLOSED")], []):  # second run finds nothing
        with session_factory() as session:
            closed = finalize_due_auctions(session, clock)
            session.commit()
        assert [(rfq_id, event.value) for rfq_id, event in closed] == expected

    closing = detail(client, rfq, users["buyer"])["events"][0]
    assert closing["event_type"] == "AUCTION_CLOSED"
    assert closing["created_at"] == iso(CLOSE)
    assert closing["message"] == "Closed. L1: Saffron at ₹4,80,000 (2 suppliers, 2 bids, 0 extensions)."


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #


def test_listing_orders_live_auctions_first(client, users, clock):
    clock.set(NOW - timedelta(hours=3))
    finished = create_rfq(
        client,
        users,
        name="Finished",
        bid_start_at=iso(NOW - timedelta(hours=3)),
        bid_close_at=iso(NOW - timedelta(hours=2)),
        forced_close_at=iso(NOW - timedelta(hours=1)),
    )
    clock.set(NOW)
    upcoming = create_rfq(client, users, name="Upcoming", bid_start_at=iso(NOW + timedelta(minutes=30)))
    live = create_rfq(client, users, name="Live")
    place_bid(client, live, users["kestrel"], 500_000)
    place_bid(client, live, users["kestrel"], 480_000)
    place_bid(client, live, users["saffron"], 490_000)

    listing = client.get("/api/rfqs", headers=as_user(users["buyer"])).json()
    assert [(r["id"], r["status"]) for r in listing] == [
        (live["id"], "ACTIVE"),
        (upcoming["id"], "UPCOMING"),
        (finished["id"], "CLOSED"),
    ]
    expected = {"lowest_bid": "480000.00", "l1_supplier": "Kestrel", "bid_count": 3, "supplier_count": 2}
    assert {key: listing[0][key] for key in expected} == expected
    assert listing[1]["lowest_bid"] is None
