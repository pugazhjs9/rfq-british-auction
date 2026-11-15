import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { projectedRank } from '../lib/auction.js';
import { formatDate, formatDateTime, formatMoney } from '../lib/format.js';

const CHARGES = [
  ['freight_charges', 'Freight'],
  ['origin_charges', 'Origin charges'],
  ['destination_charges', 'Destination charges'],
];

function initialForm(mine, pickupDate) {
  return {
    carrier_name: mine?.carrier_name ?? '',
    freight_charges: '',
    origin_charges: '',
    destination_charges: '',
    transit_time_days: mine?.transit_time_days ?? '',
    quote_valid_until: mine?.quote_valid_until ?? pickupDate,
  };
}

/** Quote submission for the supplier you're acting as. Remount it (key) when that changes. */
export function BidForm({ rfq, status, user, now, onPlaced }) {
  const mine = rfq.ranking.find((r) => r.supplier?.id === user.id);
  const [form, setForm] = useState(() => initialForm(mine, rfq.pickup_date));
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const amounts = CHARGES.map(([key]) => form[key]);
  const complete = amounts.every((v) => v !== '' && Number(v) >= 0);
  const total = complete ? amounts.reduce((sum, v) => sum + Number(v), 0) : null;
  const notLower = mine && total != null && total >= Number(mine.total_amount);
  const rank = total != null && total > 0 && !notLower ? projectedRank(rfq.ranking, user.id, total) : null;
  const open = status === 'ACTIVE';

  const update = (key) => (event) => {
    setForm((f) => ({ ...f, [key]: event.target.value }));
    setErrors((e) => ({ ...e, [key]: undefined, _: undefined }));
  };

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setNotice(null);
    try {
      const result = await api.placeBid(
        rfq.id,
        { ...form, transit_time_days: Number(form.transit_time_days) },
        user.id,
      );
      setNotice(result);
      setErrors({});
      setForm((f) => ({ ...f, freight_charges: '', origin_charges: '', destination_charges: '' }));
      onPlaced();
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.fields).length) setErrors(error.fields);
      else setErrors({ _: error.message });
    } finally {
      setSubmitting(false);
    }
  }

  const field = (key, label, input) => (
    <label key={key} className={`field ${errors[key] ? 'field--error' : ''}`}>
      <span className="field__label">{label}</span>
      {input}
      {errors[key] && <span className="field__error">{errors[key]}</span>}
    </label>
  );

  return (
    <section className="panel panel--form" aria-labelledby="bid-heading">
      <h2 id="bid-heading">Your quote</h2>
      <p className="panel__lede">
        {mine
          ? `You're L${mine.rank} at ${formatMoney(mine.total_amount)}. A new quote must come in lower.`
          : `You haven't quoted yet. Bidding as ${user.company}.`}
      </p>

      {!open && (
        <p className="notice notice--muted">
          {status === 'UPCOMING'
            ? `Bidding opens at ${formatDateTime(rfq.bid_start_at, now)}.`
            : 'Bidding has closed for this RFQ.'}
        </p>
      )}

      <form onSubmit={submit} noValidate>
        <fieldset disabled={!open || submitting}>
          {field(
            'carrier_name',
            'Carrier',
            <input value={form.carrier_name} onChange={update('carrier_name')} placeholder="e.g. Maersk" required />,
          )}
          <div className="field-grid">
            {CHARGES.map(([key, label]) =>
              field(
                key,
                `${label} (₹)`,
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={form[key]}
                  onChange={update(key)}
                  required
                />,
              ),
            )}
            {field(
              'transit_time_days',
              'Transit time (days)',
              <input
                type="number"
                inputMode="numeric"
                min="1"
                step="1"
                value={form.transit_time_days}
                onChange={update('transit_time_days')}
                required
              />,
            )}
          </div>
          {field(
            'quote_valid_until',
            `Quote valid until (pickup ${formatDate(rfq.pickup_date)})`,
            <input
              type="date"
              min={rfq.pickup_date}
              value={form.quote_valid_until}
              onChange={update('quote_valid_until')}
              required
            />,
          )}

          <div className="quote-total" aria-live="polite">
            <span>Total</span>
            {total != null ? <strong>{formatMoney(total)}</strong> : <span className="quote-total__empty">Enter all three charges</span>}
            {notLower && <em className="quote-total__warn">Must be below your current {formatMoney(mine.total_amount)}</em>}
            {rank != null && <em>This would rank L{rank}</em>}
          </div>

          {errors._ && <p className="notice notice--error">{errors._}</p>}
          {notice && (
            <p className="notice notice--ok">
              Bid placed. You're L{notice.rank}.
              {notice.extended && ` The close moved to ${formatDateTime(notice.current_close_at, now, { seconds: true })}.`}
            </p>
          )}

          <button type="submit" className="button button--primary button--block" disabled={!complete || notLower}>
            {submitting ? 'Placing bid…' : 'Place bid'}
          </button>
        </fieldset>
      </form>
    </section>
  );
}
