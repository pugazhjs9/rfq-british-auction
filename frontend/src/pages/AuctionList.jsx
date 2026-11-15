import { useState } from 'react';
import { Link } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge.jsx';
import { useActingUser } from '../hooks/actingUser.jsx';
import { useLiveFeed, usePolling, useResource } from '../hooks/data.js';
import { useNow } from '../hooks/serverClock.jsx';
import { api } from '../lib/api.js';
import { inTriggerWindow, statusAt } from '../lib/auction.js';
import { formatCountdown, formatDateTime, formatMoney, formatSpan, timeZoneLabel, toMs } from '../lib/format.js';

const FILTERS = [
  { key: 'ALL', label: 'All', matches: () => true },
  { key: 'ACTIVE', label: 'Active', matches: (s) => s === 'ACTIVE' },
  { key: 'UPCOMING', label: 'Upcoming', matches: (s) => s === 'UPCOMING' },
  { key: 'CLOSED', label: 'Closed', matches: (s) => s === 'CLOSED' || s === 'FORCE_CLOSED' },
];

export default function AuctionList() {
  const now = useNow();
  const { user } = useActingUser();
  const { data, error, loading, reload } = useResource(() => api.auctions(user.id), [user.id]);
  const connected = useLiveFeed('/ws/rfqs', reload);
  usePolling(reload, connected ? 30_000 : 5_000);
  const [filter, setFilter] = useState('ALL');

  const auctions = (data ?? []).map((a) => ({ ...a, status: statusAt(now, a) }));
  const visible = auctions.filter((a) => FILTERS.find((f) => f.key === filter).matches(a.status));

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Auctions</h1>
          <p className="muted">Times shown in {timeZoneLabel()}.</p>
        </div>
        {user.role === 'BUYER' && (
          <Link to="/rfqs/new" className="button button--primary">
            New RFQ
          </Link>
        )}
      </header>

      {data && <Summary auctions={auctions} user={user} now={now} />}

      <div className="toggle toggle--filters" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label} <span className="toggle__count">{auctions.filter((a) => f.matches(a.status)).length}</span>
          </button>
        ))}
      </div>

      {error && !data && <p className="notice notice--error">Couldn't load auctions: {error.message}</p>}
      {loading && !data && <p className="muted">Loading auctions…</p>}

      {data && (
        <div className="sheet">
          {visible.length === 0 ? (
            <p className="empty">
              No auctions here.{' '}
              {user.role === 'BUYER' ? <Link to="/rfqs/new">Create an RFQ</Link> : 'Check another filter.'}
            </p>
          ) : (
            <div className="table-scroll">
              <table className="table table--auctions">
                <thead>
                  <tr>
                    <th scope="col">RFQ</th>
                    <th scope="col" className="num">Lowest bid</th>
                    <th scope="col">Current close</th>
                    <th scope="col">Forced close</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((a) => (
                    <AuctionRow key={a.id} auction={a} user={user} now={now} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}

/**
 * Totals across every auction. Buyers see what late bidding added and saved;
 * suppliers see where they stand. Computed from the listing itself.
 */
function Summary({ auctions, user, now }) {
  const live = auctions.filter((a) => a.status === 'ACTIVE');
  const nextClose = Math.min(...live.map((a) => toMs(a.current_close_at)));
  const liveTile = (
    <Stat
      label="Live now"
      value={live.length}
      note={live.length ? `Next one closes in ${formatCountdown(nextClose - now)}` : 'No auction is taking bids'}
    />
  );

  if (user.role === 'SUPPLIER') {
    const quoted = live.filter((a) => a.my_rank != null);
    const leading = quoted.filter((a) => a.my_rank === 1);
    return (
      <section className="stats" aria-label="Your auctions">
        {liveTile}
        <Stat
          label="You're L1 on"
          value={leading.length}
          tone={leading.length ? 'lead' : ''}
          note={quoted.length ? `of the ${quoted.length} live ${plural(quoted.length, 'auction')} you've bid on` : "You haven't bid on a live auction"}
        />
        <Stat
          label="Waiting for your quote"
          value={live.length - quoted.length}
          note={`Live ${plural(live.length - quoted.length, 'auction')} you haven't bid on`}
        />
      </section>
    );
  }

  const british = auctions.filter((a) => a.british_auction);
  const added = british.reduce((sum, a) => sum + toMs(a.current_close_at) - toMs(a.bid_close_at), 0);
  const extensions = british.reduce((sum, a) => sum + a.extension_count, 0);
  const extended = british.filter((a) => a.extension_count > 0).length;
  const bidOn = auctions.filter((a) => a.lowest_bid != null);
  const firstQuotes = bidOn.reduce((sum, a) => sum + Number(a.best_first_quote), 0);
  const saved = firstQuotes - bidOn.reduce((sum, a) => sum + Number(a.lowest_bid), 0);
  return (
    <section className="stats" aria-label="Across all auctions">
      {liveTile}
      <Stat
        label="Time added by late bids"
        value={extensions ? `+${formatSpan(added)}` : 'None'}
        tone={extensions ? 'signal' : ''}
        note={extensions ? `${extensions} ${plural(extensions, 'extension')} on ${extended} ${plural(extended, 'auction')}` : 'No auction has been extended'}
      />
      <Stat
        label="Saved by bidding"
        value={formatMoney(Math.round(saved))}
        tone={saved > 0 ? 'lead' : ''}
        note={firstQuotes ? `${((saved / firstQuotes) * 100).toFixed(1)}% under the best first quotes` : 'No bids yet'}
        title="Compared with the lowest of each supplier's first quote: the price before anyone bid again."
      />
    </section>
  );
}

function Stat({ label, value, note, tone = '', title }) {
  return (
    <div className={`stat ${tone ? `stat--${tone}` : ''}`} title={title}>
      <p className="stat__label">{label}</p>
      <p className="stat__value">{value}</p>
      <p className="stat__note">{note}</p>
    </div>
  );
}

const plural = (count, noun) => (count === 1 ? noun : `${noun}s`);

function AuctionRow({ auction: a, user, now }) {
  const close = toMs(a.current_close_at);
  const hot = a.status === 'ACTIVE' && inTriggerWindow(now, a);
  return (
    <tr className="row-link">
      <td>
        <span className="sub">{a.reference_id}</span>
        <Link to={`/rfqs/${a.id}`} className="row-link__target">
          {a.name}
        </Link>
      </td>
      <td className="num">
        {a.lowest_bid != null ? (
          <>
            <span className="total">{formatMoney(a.lowest_bid)}</span>
            <Standing auction={a} user={user} />
          </>
        ) : (
          <span className="muted">No bids yet</span>
        )}
      </td>
      <td>
        {formatDateTime(close, now)}
        {a.status === 'ACTIVE' && (
          <span className={`sub ${hot ? 'sub--hot' : ''}`}>in {formatCountdown(close - now)}</span>
        )}
        {a.status === 'UPCOMING' && <span className="sub">opens {formatDateTime(a.bid_start_at, now)}</span>}
        {a.extension_count > 0 && (
          <span className="sub sub--signal">
            extended {a.extension_count} {a.extension_count === 1 ? 'time' : 'times'}
          </span>
        )}
      </td>
      <td>
        {a.british_auction ? (
          formatDateTime(a.forced_close_at, now)
        ) : (
          <>
            <span className="muted">None</span>
            <span className="sub">Fixed close</span>
          </>
        )}
      </td>
      <td>
        <StatusBadge status={a.status} />
      </td>
    </tr>
  );
}

/** Under the lowest bid: who holds it (buyers), or where you stand (suppliers). */
function Standing({ auction: a, user }) {
  if (user.role === 'BUYER') return <span className="sub">{a.l1_supplier}</span>;
  if (a.my_rank == null) return <span className="sub">You haven't bid</span>;
  return <span className={`sub ${a.my_rank === 1 ? 'sub--lead' : ''}`}>You're L{a.my_rank}</span>;
}
