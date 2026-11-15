import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ActivityLog } from '../components/ActivityLog.jsx';
import { BidForm } from '../components/BidForm.jsx';
import { Countdown } from '../components/Countdown.jsx';
import { EndgameTrack } from '../components/EndgameTrack.jsx';
import { RankingTable } from '../components/RankingTable.jsx';
import { RulesPanel } from '../components/RulesPanel.jsx';
import { StatusBadge } from '../components/StatusBadge.jsx';
import { useActingUser } from '../hooks/actingUser.jsx';
import { useLiveFeed, usePolling, useResource } from '../hooks/data.js';
import { useClockOffset, useNow } from '../hooks/serverClock.jsx';
import { api } from '../lib/api.js';
import { statusAt } from '../lib/auction.js';
import { formatDate, toMs } from '../lib/format.js';

export default function AuctionDetail() {
  const { id } = useParams();
  const now = useNow();
  const offset = useClockOffset();
  const { user } = useActingUser();
  const { data: rfq, error, reload } = useResource(() => api.auction(id, user.id), [id, user.id]);
  const connected = useLiveFeed(`/ws/rfqs/${id}`, reload);
  usePolling(reload, connected ? 30_000 : 5_000);
  const justExtended = useExtensionFlash(rfq?.current_close_at);

  // Refetch just after the close passes, so the closing event shows up promptly.
  const closeAt = rfq?.current_close_at;
  useEffect(() => {
    if (!closeAt) return undefined;
    const wait = toMs(closeAt) - (Date.now() + offset);
    if (wait < 0) return undefined;
    const timer = setTimeout(reload, wait + 6_000);
    return () => clearTimeout(timer);
  }, [closeAt, offset, reload]);

  if (!rfq) {
    if (error) {
      return (
        <div className="page-message">
          <h1>{error.status === 404 ? "This RFQ doesn't exist" : "Couldn't load this RFQ"}</h1>
          <p className="muted">{error.status === 404 ? 'It may have been removed, or the link is wrong.' : error.message}</p>
          <Link to="/" className="button">Back to auctions</Link>
        </div>
      );
    }
    return <p className="muted">Loading auction…</p>;
  }

  const status = statusAt(now, rfq);
  const extensions = rfq.events
    .filter((e) => e.event_type === 'EXTENDED')
    .map((e) => ({ from: toMs(e.previous_close_at), to: toMs(e.new_close_at) }))
    .reverse();

  return (
    <>
      <Link to="/" className="backlink">All auctions</Link>

      <header className="auction-head">
        <div className="auction-head__title">
          <p className="auction-head__ref">
            <span>{rfq.reference_id}</span>
            <span>{rfq.british_auction ? 'British auction' : 'Fixed close'}</span>
            <StatusBadge status={status} />
            <span className={`live ${connected ? 'live--on' : ''}`}>
              {connected ? 'Live updates on' : 'Reconnecting…'}
            </span>
          </p>
          <h1>{rfq.name}</h1>
          <p className="muted">
            Pickup {formatDate(rfq.pickup_date)}. Requested by {rfq.buyer.company}.
          </p>
        </div>
        <Countdown rfq={rfq} status={status} now={now} flash={justExtended} />
      </header>

      {rfq.british_auction && (
        <EndgameTrack
          start={toMs(rfq.bid_start_at)}
          scheduledClose={toMs(rfq.bid_close_at)}
          currentClose={toMs(rfq.current_close_at)}
          forcedClose={toMs(rfq.forced_close_at)}
          windowMinutes={rfq.trigger_window_minutes}
          extensions={extensions}
          now={now}
          flash={justExtended}
        />
      )}

      <div className="auction-body">
        <div className="sheet">
          <RankingTable ranking={rfq.ranking} bids={rfq.bids} currentUserId={user.id} now={now} />
          <ActivityLog events={rfq.events} now={now} />
        </div>
        <aside className="auction-side">
          {user.role === 'SUPPLIER' ? (
            <BidForm key={user.id} rfq={rfq} status={status} user={user} now={now} onPlaced={reload} />
          ) : (
            <section className="panel">
              <h2>Buyer view</h2>
              <p className="panel__lede">
                You see every supplier by name. Suppliers see each other only as Supplier A, B, C. To bid,
                use Switch account and pick a supplier; you'll come back to this page.
              </p>
            </section>
          )}
          <RulesPanel rfq={rfq} now={now} />
        </aside>
      </div>
    </>
  );
}

/** True for a moment after the close time moves later, so the change is visible. */
function useExtensionFlash(closeAt) {
  const previous = useRef(closeAt);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    const before = previous.current;
    previous.current = closeAt;
    if (!before || !closeAt || toMs(closeAt) <= toMs(before)) return undefined;
    setFlash(true);
    const timer = setTimeout(() => setFlash(false), 2_400);
    return () => clearTimeout(timer);
  }, [closeAt]);
  return flash;
}
