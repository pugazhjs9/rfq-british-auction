import { toMs } from './format.js';

export const MINUTE = 60_000;

/** Mirrors engine.auction_status on the server so the UI flips on the exact second. */
export function statusAt(now, rfq) {
  if (now < toMs(rfq.bid_start_at)) return 'UPCOMING';
  const close = toMs(rfq.current_close_at);
  if (now < close) return 'ACTIVE';
  // Without the British auction option there is no forced close to reach.
  return rfq.forced_close_at && close >= toMs(rfq.forced_close_at) ? 'FORCE_CLOSED' : 'CLOSED';
}

export const STATUS_LABEL = {
  UPCOMING: 'Upcoming',
  ACTIVE: 'Active',
  CLOSED: 'Closed',
  FORCE_CLOSED: 'Force closed',
};

export const TRIGGERS = {
  BID_RECEIVED: {
    label: 'Any bid',
    phrase: 'Any bid',
    description: 'Every bid in the trigger window extends the auction.',
  },
  ANY_RANK_CHANGE: {
    label: 'Any rank change',
    phrase: "A bid that changes any supplier's rank",
    description: 'Extends when a bid reorders the ranking, including a new supplier joining it.',
  },
  L1_CHANGE: {
    label: 'L1 change',
    phrase: 'A bid that changes the L1 supplier',
    description: 'Extends only when a different supplier becomes the lowest bidder.',
  },
};

export function describeRules({ british_auction, trigger_type, trigger_window_minutes, extension_minutes }) {
  if (!british_auction) return "Fixed close: bidding ends at the close time and late bids don't extend it.";
  return `${TRIGGERS[trigger_type].phrase} in the last ${trigger_window_minutes} min extends the close by ${extension_minutes} min, never past the forced close time.`;
}

export function inTriggerWindow(now, rfq) {
  if (!rfq.british_auction) return false;
  const close = toMs(rfq.current_close_at);
  return close - rfq.trigger_window_minutes * MINUTE <= now && now < close;
}

/**
 * Rank a supplier would get with `total`. The ranking is sorted cheapest first,
 * and an existing bid at the same price keeps its place (it got there first),
 * so the answer is 1 + the number of other suppliers at or below `total`:
 * an upper-bound binary search.
 */
export function projectedRank(ranking, supplierId, total) {
  const totals = ranking.filter((r) => r.supplier?.id !== supplierId).map((r) => Number(r.total_amount));
  let lo = 0;
  let hi = totals.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (totals[mid] <= total) lo = mid + 1;
    else hi = mid;
  }
  return lo + 1;
}

/** "IR" for Indigo Retail: initials of the first two words. */
export function monogram(company) {
  return company
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase();
}
