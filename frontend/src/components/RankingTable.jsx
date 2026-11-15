import { useState } from 'react';
import { formatMoney, formatShortDate, formatTime, otherDay } from '../lib/format.js';

export function RankingTable({ ranking, bids, currentUserId, now }) {
  const [view, setView] = useState('ranking');
  const rows = view === 'ranking' ? ranking : bids;
  const someHidden = bids.some((b) => b.supplier == null);

  return (
    <section className="sheet__section" aria-labelledby="ranking-heading">
      <div className="section-head">
        <h2 id="ranking-heading">Bids</h2>
        <div className="toggle" role="group" aria-label="Which bids to show">
          <button type="button" aria-pressed={view === 'ranking'} onClick={() => setView('ranking')}>
            Current ranking
          </button>
          <button type="button" aria-pressed={view === 'all'} onClick={() => setView('all')}>
            All bids ({bids.length})
          </button>
        </div>
      </div>
      {someHidden && (
        <p className="section-note">
          Other suppliers are shown as Supplier A, B, C, in the order they first bid. Only the buyer sees their names.
        </p>
      )}

      {rows.length === 0 ? (
        <p className="empty">No bids yet. Quotes will appear here, cheapest first.</p>
      ) : (
        <div className="table-scroll">
          <table className="table table--bids">
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Supplier</th>
                <th scope="col" className="num">Freight</th>
                <th scope="col" className="num">Origin</th>
                <th scope="col" className="num">Destination</th>
                <th scope="col" className="num">Total</th>
                <th scope="col" className="num">Transit</th>
                <th scope="col">Valid until</th>
                <th scope="col">Bid at</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((bid) => {
                const mine = bid.supplier?.id === currentUserId;
                const leader = bid.rank === 1;
                return (
                  <tr
                    key={bid.id}
                    className={[leader && 'is-leader', bid.rank == null && 'is-superseded', mine && 'is-mine']
                      .filter(Boolean)
                      .join(' ')}
                  >
                    <td>
                      {bid.rank != null ? <span className="rank">L{bid.rank}</span> : <span className="muted">Replaced</span>}
                      {view === 'ranking' && bid.revisions > 1 && <span className="sub">{bid.revisions} bids</span>}
                    </td>
                    <td>
                      <span className={`supplier ${bid.supplier ? '' : 'supplier--alias'}`}>
                        {bid.bidder}
                        {mine && <span className="tag">You</span>}
                      </span>
                      {bid.carrier_name && <span className="sub">{bid.carrier_name}</span>}
                    </td>
                    <td className="num">{formatMoney(bid.freight_charges)}</td>
                    <td className="num">{formatMoney(bid.origin_charges)}</td>
                    <td className="num">{formatMoney(bid.destination_charges)}</td>
                    <td className="num total">{formatMoney(bid.total_amount)}</td>
                    <td className="num">{bid.transit_time_days} d</td>
                    <td>{formatShortDate(bid.quote_valid_until, now)}</td>
                    <td>
                      {formatTime(bid.created_at, { seconds: true })}
                      {otherDay(bid.created_at, now) && <span className="sub">{otherDay(bid.created_at, now)}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
