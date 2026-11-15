"""Unit tests for the pure auction rules. No database needed."""

import itertools
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine import (
    AuctionStatus,
    ExtensionRules,
    Standing,
    TriggerType,
    apply_bid,
    auction_status,
    decide_extension,
    in_trigger_window,
    rank,
)

T0 = datetime(2026, 1, 15, 17, 0, tzinfo=UTC)
CLOSE = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
FORCED = datetime(2026, 1, 15, 18, 20, tzinfo=UTC)


def at(minutes: float) -> datetime:
    """Minutes relative to the 18:00 close: at(-5) is 17:55."""
    return CLOSE + timedelta(minutes=minutes)


_bid_ids = itertools.count(1)


def standing(supplier: int, total: int, minute: float = -30) -> Standing:
    return Standing(supplier, Decimal(total), at(minute), next(_bid_ids))


def rules(trigger=TriggerType.BID_RECEIVED, window=10, extension=5) -> ExtensionRules:
    return ExtensionRules(timedelta(minutes=window), timedelta(minutes=extension), trigger)


def suppliers(ranking: list[Standing]) -> list[int]:
    return [s.supplier_id for s in ranking]


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("now", "current_close", "expected"),
    [
        (T0 - timedelta(seconds=1), CLOSE, AuctionStatus.UPCOMING),
        (T0, CLOSE, AuctionStatus.ACTIVE),  # opens exactly at start
        (CLOSE - timedelta(microseconds=1), CLOSE, AuctionStatus.ACTIVE),
        (CLOSE, CLOSE, AuctionStatus.CLOSED),  # closes exactly at close
        (at(10), at(5), AuctionStatus.CLOSED),  # extended once, then went quiet
        (FORCED, FORCED, AuctionStatus.FORCE_CLOSED),  # extensions reached the cap
    ],
)
def test_status(now, current_close, expected):
    assert auction_status(now, T0, current_close, FORCED) is expected


def test_without_british_auction_status_is_never_force_closed():
    assert auction_status(CLOSE - timedelta(seconds=1), T0, CLOSE, None) is AuctionStatus.ACTIVE
    assert auction_status(CLOSE, T0, CLOSE, None) is AuctionStatus.CLOSED


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


def test_rank_orders_by_price_then_time():
    ranking = rank([standing(1, 500, -20), standing(2, 400, -10), standing(3, 400, -15)])
    assert suppliers(ranking) == [3, 2, 1]  # 3 and 2 tie on price; 3 got there first


def test_first_bid_is_l1_and_a_rank_change():
    change = apply_bid([], standing(1, 500))
    assert suppliers(change.after) == [1]
    assert change.old_position is None and change.new_position == 0
    assert change.rank_changed and change.l1_changed


def test_newcomer_at_bottom_changes_ranks_but_not_l1():
    before = rank([standing(1, 400), standing(2, 450)])
    change = apply_bid(before, standing(3, 500, -5))
    assert suppliers(change.after) == [1, 2, 3]
    assert change.rank_changed and not change.l1_changed


def test_improving_without_passing_anyone_changes_nothing():
    before = rank([standing(1, 400), standing(2, 450), standing(3, 500)])
    change = apply_bid(before, standing(3, 480, -5))
    assert suppliers(change.after) == [1, 2, 3]
    assert (change.old_position, change.new_position) == (2, 2)
    assert not change.rank_changed and not change.l1_changed


def test_l1_lowering_own_price_is_not_an_l1_change():
    before = rank([standing(1, 400), standing(2, 450)])
    change = apply_bid(before, standing(1, 300, -5))
    assert suppliers(change.after) == [1, 2]
    assert not change.rank_changed and not change.l1_changed


def test_passing_a_supplier_below_l1():
    before = rank([standing(1, 400), standing(2, 450), standing(3, 500)])
    change = apply_bid(before, standing(3, 420, -5))
    assert suppliers(change.after) == [1, 3, 2]
    assert change.rank_changed and not change.l1_changed


def test_taking_l1():
    before = rank([standing(1, 400), standing(2, 450)])
    change = apply_bid(before, standing(2, 390, -5))
    assert suppliers(change.after) == [2, 1]
    assert change.previous_l1.supplier_id == 1
    assert change.rank_changed and change.l1_changed


def test_matching_l1_price_ranks_behind_the_earlier_bid():
    before = rank([standing(1, 400, -20), standing(2, 450, -20)])
    change = apply_bid(before, standing(2, 400, -5))
    assert suppliers(change.after) == [1, 2]
    assert not change.l1_changed


def test_incremental_ranking_matches_brute_force():
    """Fuzz apply_bid against the obvious O(n log n) re-sort and rank-map comparison."""
    rng = random.Random(7)
    for _ in range(300):
        ranking: list[Standing] = []
        best: dict[int, int] = {}
        for step in range(40):
            supplier = rng.randint(1, 8)
            ceiling = best.get(supplier, 10_000)
            total = rng.randint(max(ceiling - 400, 1), ceiling - 1) if ceiling > 1 else None
            if total is None:
                continue
            best[supplier] = total
            bid = Standing(supplier, Decimal(total), T0 + timedelta(seconds=step), step)

            change = apply_bid(ranking, bid)

            expected = rank([s for s in ranking if s.supplier_id != supplier] + [bid])
            assert change.after == expected
            ranks_before = {s.supplier_id: i for i, s in enumerate(ranking)}
            ranks_after = {s.supplier_id: i for i, s in enumerate(expected)}
            assert change.rank_changed == any(
                ranks_before.get(s) != r for s, r in ranks_after.items()
            )
            assert change.l1_changed == (not ranking or ranking[0].supplier_id != expected[0].supplier_id)
            ranking = change.after


# --------------------------------------------------------------------------- #
# Trigger window
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("minute", "inside"),
    [(-10.01, False), (-10, True), (-0.01, True), (0, False)],
)
def test_trigger_window_is_half_open(minute, inside):
    assert in_trigger_window(at(minute), CLOSE, timedelta(minutes=10)) is inside


# --------------------------------------------------------------------------- #
# Extension decisions
# --------------------------------------------------------------------------- #


def test_bid_outside_window_never_extends():
    change = apply_bid([], standing(1, 500, -11))
    assert decide_extension(at(-11), CLOSE, FORCED, rules(), change) is None


def test_bid_received_extends_from_current_close():
    change = apply_bid([], standing(1, 500, -5))
    extension = decide_extension(at(-5), CLOSE, FORCED, rules(), change)
    assert extension.new_close_at == at(5)  # 18:00 -> 18:05, as in the spec
    assert extension.extended and not extension.capped


def test_window_moves_with_each_extension():
    # After 18:00 -> 18:05 the window is 17:55-18:05, so a bid at 18:02 counts.
    change = apply_bid([standing(1, 500)], standing(2, 450, 2))
    extension = decide_extension(at(2), at(5), FORCED, rules(), change)
    assert extension.new_close_at == at(10)


def test_extension_is_capped_at_forced_close():
    change = apply_bid([], standing(1, 500, 17))
    extension = decide_extension(at(17), at(18), FORCED, rules(), change)
    assert extension.new_close_at == FORCED
    assert extension.applied == timedelta(minutes=2)
    assert extension.capped


def test_trigger_at_forced_close_does_not_extend():
    change = apply_bid([], standing(1, 500, 19))
    extension = decide_extension(at(19), FORCED, FORCED, rules(), change)
    assert extension is not None and not extension.extended
    assert extension.new_close_at == FORCED


def test_rank_change_trigger_ignores_bids_that_keep_the_order():
    before = rank([standing(1, 400), standing(2, 450)])
    quiet = apply_bid(before, standing(2, 420, -3))
    assert decide_extension(at(-3), CLOSE, FORCED, rules(TriggerType.ANY_RANK_CHANGE), quiet) is None

    overtaking = apply_bid(before, standing(2, 390, -3))
    assert decide_extension(at(-3), CLOSE, FORCED, rules(TriggerType.ANY_RANK_CHANGE), overtaking)


def test_l1_trigger_ignores_changes_below_l1():
    before = rank([standing(1, 400), standing(2, 450), standing(3, 500)])
    below = apply_bid(before, standing(3, 420, -3))  # L3 -> L2
    assert decide_extension(at(-3), CLOSE, FORCED, rules(TriggerType.L1_CHANGE), below) is None

    top = apply_bid(before, standing(3, 399, -3))  # L3 -> L1
    assert decide_extension(at(-3), CLOSE, FORCED, rules(TriggerType.L1_CHANGE), top).new_close_at == at(5)


def test_chain_of_extensions_never_passes_forced_close():
    """Keep bidding at the last second; the close must stop exactly at the forced time."""
    close, ranking = CLOSE, []
    for i in range(20):
        now = close - timedelta(seconds=1)
        change = apply_bid(ranking, Standing(i % 3, Decimal(1000 - i), now, i))
        extension = decide_extension(now, close, FORCED, rules(), change)
        assert extension is not None
        assert extension.new_close_at <= FORCED
        close, ranking = extension.new_close_at, change.after
    assert close == FORCED
