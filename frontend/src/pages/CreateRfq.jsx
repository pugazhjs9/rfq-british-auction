import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { EndgameTrack } from '../components/EndgameTrack.jsx';
import { useActingUser } from '../hooks/actingUser.jsx';
import { useNow } from '../hooks/serverClock.jsx';
import { ApiError, api } from '../lib/api.js';
import { MINUTE, TRIGGERS, describeRules } from '../lib/auction.js';
import { formatDateTime, timeZoneLabel, toLocalDate, toLocalInput } from '../lib/format.js';

const AUCTION_TYPES = [
  {
    british: true,
    label: 'British auction',
    description: 'Late bids extend the close, up to a forced close time you set.',
  },
  {
    british: false,
    label: 'Fixed close',
    description: 'Bidding ends at the close time, whatever happens near the end.',
  },
];

function defaults(now) {
  const start = Math.ceil(now / (5 * MINUTE)) * 5 * MINUTE;
  const close = start + 30 * MINUTE;
  const forced = close + 15 * MINUTE;
  return {
    name: '',
    british_auction: true,
    bid_start_at: toLocalInput(start),
    bid_close_at: toLocalInput(close),
    forced_close_at: toLocalInput(forced),
    pickup_date: toLocalDate(forced + 3 * 24 * 60 * MINUTE),
    trigger_window_minutes: 10,
    extension_minutes: 5,
    trigger_type: 'BID_RECEIVED',
  };
}

const parseLocal = (value) => (value ? new Date(value).getTime() : NaN);

/** The same schedule rules the API enforces, checked as you type. */
function validate(form, now) {
  const errors = {};
  const start = parseLocal(form.bid_start_at);
  const close = parseLocal(form.bid_close_at);
  const forced = parseLocal(form.forced_close_at);
  if (form.name.trim().length < 3) errors.name = 'Give the RFQ a name of at least 3 characters';
  if (Number.isNaN(start)) errors.bid_start_at = 'Choose when bidding opens';
  if (Number.isNaN(close)) errors.bid_close_at = 'Choose when bidding closes';
  else if (close <= start) errors.bid_close_at = 'Bid close time must be after the bid start time';
  else if (close <= now) errors.bid_close_at = 'Bid close time must be in the future';
  if (form.british_auction) {
    if (Number.isNaN(forced)) errors.forced_close_at = 'Choose the forced close time';
    else if (forced <= close) errors.forced_close_at = 'Forced close time must be later than the bid close time';
    for (const key of ['trigger_window_minutes', 'extension_minutes']) {
      const n = Number(form[key]);
      if (!Number.isInteger(n) || n < 1 || n > 240) errors[key] = 'Enter whole minutes between 1 and 240';
    }
  }
  const lastClose = form.british_auction ? forced : close;
  if (!form.pickup_date) errors.pickup_date = 'Choose the pickup date';
  else if (!Number.isNaN(lastClose) && form.pickup_date < toLocalDate(lastClose))
    errors.pickup_date = `Pickup date can't be before the auction's ${form.british_auction ? 'forced close' : 'close'} date`;
  return errors;
}

export default function CreateRfq() {
  const now = useNow();
  const navigate = useNavigate();
  const { user, users } = useActingUser();
  const [form, setForm] = useState(() => defaults(Date.now()));
  const [serverErrors, setServerErrors] = useState({});
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (user && user.role !== 'BUYER') {
    const buyer = users.find((u) => u.role === 'BUYER');
    return (
      <div className="page-message">
        <h1>Only buyers create RFQs</h1>
        <p className="muted">
          You're signed in as {user.company}, a supplier. Use Switch account in the top bar and pick{' '}
          {buyer?.company ?? 'a buyer'} to create one.
        </p>
        <Link to="/" className="button">Back to auctions</Link>
      </div>
    );
  }

  const clientErrors = validate(form, now);
  const errors = { ...(attempted ? clientErrors : {}), ...serverErrors };
  const update = (key) => (event) => {
    setForm((f) => ({ ...f, [key]: event.target.value }));
    setServerErrors((e) => ({ ...e, [key]: undefined, _: undefined }));
  };
  const setBritish = (british) => {
    setForm((f) => ({ ...f, british_auction: british }));
    setServerErrors({});
  };

  async function submit(event) {
    event.preventDefault();
    setAttempted(true);
    if (Object.keys(clientErrors).length) return;
    setSubmitting(true);
    try {
      const body = {
        name: form.name.trim(),
        british_auction: form.british_auction,
        bid_start_at: new Date(form.bid_start_at).toISOString(),
        bid_close_at: new Date(form.bid_close_at).toISOString(),
        pickup_date: form.pickup_date,
      };
      // A fixed-close RFQ has no extension settings, and the API rejects them.
      if (form.british_auction) {
        Object.assign(body, {
          forced_close_at: new Date(form.forced_close_at).toISOString(),
          trigger_type: form.trigger_type,
          trigger_window_minutes: Number(form.trigger_window_minutes),
          extension_minutes: Number(form.extension_minutes),
        });
      }
      const created = await api.createRfq(body, user.id);
      navigate(`/rfqs/${created.id}`);
    } catch (error) {
      setServerErrors(
        error instanceof ApiError && Object.keys(error.fields).length ? error.fields : { _: error.message },
      );
      setSubmitting(false);
    }
  }

  const field = (key, label, input, hint) => (
    <label className={`field ${errors[key] ? 'field--error' : ''}`}>
      <span className="field__label">{label}</span>
      {input}
      {errors[key] ? <span className="field__error">{errors[key]}</span> : hint && <span className="field__hint">{hint}</span>}
    </label>
  );

  const start = parseLocal(form.bid_start_at);
  const close = parseLocal(form.bid_close_at);
  const forced = parseLocal(form.forced_close_at);
  const windowMinutes = Number(form.trigger_window_minutes);
  const previewable = start < close && close < forced && windowMinutes > 0;

  return (
    <>
      <Link to="/" className="backlink">All auctions</Link>
      <header className="page-head">
        <div>
          <h1>New RFQ</h1>
          <p className="muted">Suppliers bid down openly. Times in {timeZoneLabel()}.</p>
        </div>
      </header>

      <form className="create" onSubmit={submit} noValidate>
        <div className="sheet create__form">
          <fieldset className="create__group" disabled={submitting}>
            <legend>Shipment</legend>
            {field(
              'name',
              'RFQ name',
              <input value={form.name} onChange={update('name')} placeholder="e.g. Nhava Sheva to Rotterdam, 2x40ft HC" />,
              'The reference ID (RFQ-00001) is assigned for you.',
            )}
            {field('pickup_date', 'Pickup / service date', <input type="date" value={form.pickup_date} onChange={update('pickup_date')} />)}
          </fieldset>

          <fieldset className="create__group" disabled={submitting}>
            <legend>Auction</legend>
            <div className="choices choices--pair" role="radiogroup" aria-label="Auction type">
              {AUCTION_TYPES.map((type) => (
                <label key={type.label} className={`choice ${form.british_auction === type.british ? 'choice--on' : ''}`}>
                  <input
                    type="radio"
                    name="auction_type"
                    checked={form.british_auction === type.british}
                    onChange={() => setBritish(type.british)}
                  />
                  <span className="choice__label">{type.label}</span>
                  <span className="choice__text">{type.description}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="create__group" disabled={submitting}>
            <legend>Schedule</legend>
            <div className="field-grid">
              {field('bid_start_at', 'Bid start', <input type="datetime-local" value={form.bid_start_at} onChange={update('bid_start_at')} />)}
              {field('bid_close_at', 'Bid close', <input type="datetime-local" value={form.bid_close_at} onChange={update('bid_close_at')} />)}
            </div>
            {form.british_auction &&
              field(
                'forced_close_at',
                'Forced bid close',
                <input type="datetime-local" value={form.forced_close_at} onChange={update('forced_close_at')} />,
                'Hard stop. Extensions can never push the close past this.',
              )}
          </fieldset>

          {form.british_auction && (
            <fieldset className="create__group" disabled={submitting}>
              <legend>Extensions</legend>
              <div className="choices" role="radiogroup" aria-label="Extension trigger">
                {Object.entries(TRIGGERS).map(([value, trigger]) => (
                  <label key={value} className={`choice ${form.trigger_type === value ? 'choice--on' : ''}`}>
                    <input
                      type="radio"
                      name="trigger_type"
                      value={value}
                      checked={form.trigger_type === value}
                      onChange={update('trigger_type')}
                    />
                    <span className="choice__label">{trigger.label}</span>
                    <span className="choice__text">{trigger.description}</span>
                  </label>
                ))}
              </div>
              <div className="field-grid">
                {field(
                  'trigger_window_minutes',
                  'Trigger window, X (min)',
                  <input type="number" min="1" max="240" value={form.trigger_window_minutes} onChange={update('trigger_window_minutes')} />,
                  'How close to the end bids are watched.',
                )}
                {field(
                  'extension_minutes',
                  'Extension, Y (min)',
                  <input type="number" min="1" max="240" value={form.extension_minutes} onChange={update('extension_minutes')} />,
                  'Time added each time the trigger fires.',
                )}
              </div>
            </fieldset>
          )}

          {errors._ && <p className="notice notice--error">{errors._}</p>}
          <button type="submit" className="button button--primary" disabled={submitting}>
            {submitting ? 'Creating RFQ…' : 'Create RFQ'}
          </button>
        </div>

        <aside className="create__preview" aria-live="polite">
          <h2>How this auction ends</h2>
          {!form.british_auction ? (
            <p className="panel__lede">
              {describeRules(form)}
              {!Number.isNaN(close) && ` This one closes at ${formatDateTime(close, now)}.`}
            </p>
          ) : previewable ? (
            <>
              <p className="panel__lede">
                {describeRules({
                  british_auction: true,
                  trigger_type: form.trigger_type,
                  trigger_window_minutes: windowMinutes,
                  extension_minutes: Number(form.extension_minutes) || 0,
                })}
              </p>
              <EndgameTrack
                start={start}
                scheduledClose={close}
                currentClose={close}
                forcedClose={forced}
                windowMinutes={windowMinutes}
                now={now}
                preview
              />
            </>
          ) : (
            <p className="muted">Set a start, close and later forced close time to see the timeline.</p>
          )}
        </aside>
      </form>
    </>
  );
}
