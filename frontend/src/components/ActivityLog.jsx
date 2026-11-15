import { useState } from 'react';
import { formatDateTime, formatTime } from '../lib/format.js';

const KIND = {
  AUCTION_CREATED: { title: 'RFQ created', tone: 'neutral' },
  BID_SUBMITTED: { title: 'Bid placed', tone: 'bid' },
  EXTENDED: { title: 'Extended', tone: 'extended' },
  EXTENSION_SKIPPED: { title: 'Not extended', tone: 'skipped' },
  AUCTION_CLOSED: { title: 'Closed', tone: 'closed' },
  AUCTION_FORCE_CLOSED: { title: 'Force-closed', tone: 'forced' },
};
const TIME_EVENTS = new Set(['EXTENDED', 'EXTENSION_SKIPPED', 'AUCTION_CLOSED', 'AUCTION_FORCE_CLOSED']);

export function ActivityLog({ events, now }) {
  const [onlyTime, setOnlyTime] = useState(false);
  const shown = onlyTime ? events.filter((e) => TIME_EVENTS.has(e.event_type)) : events;

  return (
    <section className="sheet__section" aria-labelledby="activity-heading">
      <div className="section-head">
        <h2 id="activity-heading">Activity</h2>
        <div className="toggle" role="group" aria-label="Which activity to show">
          <button type="button" aria-pressed={!onlyTime} onClick={() => setOnlyTime(false)}>
            Everything
          </button>
          <button type="button" aria-pressed={onlyTime} onClick={() => setOnlyTime(true)}>
            Time changes
          </button>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="empty">No time changes yet. Extensions and the close will be listed here.</p>
      ) : (
        <ol className="log">
          {shown.map((event) => {
            const kind = KIND[event.event_type];
            return (
              <li key={event.id} className={`log__item log__item--${kind.tone}`}>
                <time className="log__time" dateTime={event.created_at}>
                  {formatDateTime(event.created_at, now, { seconds: true })}
                </time>
                <div className="log__body">
                  <p className="log__title">{kind.title}</p>
                  <p className="log__message">{event.message}</p>
                  {event.event_type === 'EXTENDED' && (
                    <p className="log__change">
                      Close {formatTime(event.previous_close_at, { seconds: true })} →{' '}
                      {formatTime(event.new_close_at, { seconds: true })}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
