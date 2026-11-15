import { TRIGGERS, describeRules } from '../lib/auction.js';
import { formatDateTime } from '../lib/format.js';

export function RulesPanel({ rfq, now }) {
  if (!rfq.british_auction) {
    return (
      <section className="panel" aria-labelledby="rules-heading">
        <h2 id="rules-heading">Fixed close</h2>
        <p className="panel__lede">
          Bidding ends at the close time. Late bids don't extend it, so there is no forced close.
        </p>
        <dl className="facts">
          <div>
            <dt>British auction</dt>
            <dd>Off</dd>
          </div>
          <div>
            <dt>Bidding ends</dt>
            <dd>{formatDateTime(rfq.bid_close_at, now)}</dd>
          </div>
        </dl>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="rules-heading">
      <h2 id="rules-heading">Extension rules</h2>
      <p className="panel__lede">{describeRules(rfq)}</p>
      <dl className="facts">
        <div>
          <dt>Trigger window (X)</dt>
          <dd>{rfq.trigger_window_minutes} min</dd>
        </div>
        <div>
          <dt>Extension (Y)</dt>
          <dd>{rfq.extension_minutes} min</dd>
        </div>
        <div>
          <dt>Trigger</dt>
          <dd>{TRIGGERS[rfq.trigger_type].label}</dd>
        </div>
        <div>
          <dt>Extensions so far</dt>
          <dd>{rfq.extension_count}</dd>
        </div>
      </dl>
    </section>
  );
}
