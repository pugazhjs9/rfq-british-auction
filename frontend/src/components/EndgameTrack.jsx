import { MINUTE } from '../lib/auction.js';
import { formatDateTime, formatMinutes } from '../lib/format.js';

const clamp01 = (x) => Math.min(1, Math.max(0, x));

/**
 * The end of the auction drawn to scale: scheduled bidding, extensions added
 * so far, the trigger window trailing the current close, and the room left
 * before the forced close wall. All times are epoch ms.
 *
 * Only the endgame is drawn. A 10-minute window would be invisible on a
 * three-day auction, so the track starts a little before the scheduled close
 * (as far back as the extension zone is long, at least two trigger windows).
 */
export function EndgameTrack({
  start,
  scheduledClose,
  currentClose,
  forcedClose,
  windowMinutes,
  extensions = [],
  now,
  flash = false,
  preview = false,
}) {
  const windowMs = windowMinutes * MINUTE;
  const leadIn = Math.max(forcedClose - scheduledClose, 2 * windowMs);
  const from = Math.max(start, scheduledClose - leadIn);
  const span = forcedClose - from;
  if (!(span > 0)) return null;

  const at = (t) => clamp01((t - from) / span);
  const segment = (a, b) => ({ left: `${at(a) * 100}%`, width: `${(at(b) - at(a)) * 100}%` });
  const showNow = now != null && now >= from && now <= forcedClose;
  const extendedBy = currentClose - scheduledClose;
  const roomLeft = forcedClose - currentClose;

  return (
    <figure className="track" aria-label="Auction endgame timeline">
      <div className="track__bar">
        <div className="track__bidding" style={segment(from, scheduledClose)} />
        {extensions.map((e, i) => (
          <div
            key={`${e.from}-${e.to}`}
            className={`track__extension ${flash && i === extensions.length - 1 ? 'track__extension--new' : ''}`}
            style={segment(e.from, e.to)}
          />
        ))}
        <div className="track__headroom" style={segment(currentClose, forcedClose)} />
        <div className="track__tick" style={{ left: `${at(scheduledClose) * 100}%` }} />
        <div className="track__window" style={segment(currentClose - windowMs, currentClose)} />
        {showNow && <div className="track__elapsed" style={segment(from, now)} />}
        {showNow && (
          <div className="track__now" style={{ left: `${at(now) * 100}%` }}>
            <span>now</span>
          </div>
        )}
        <div className="track__wall" />
      </div>
      <dl className="track__legend">
        <div>
          <dt><i className="swatch swatch--bidding" />Bidding opened</dt>
          <dd>{formatDateTime(start, now)}</dd>
        </div>
        <div>
          <dt><i className="swatch swatch--window" />Trigger window</dt>
          <dd>Last {windowMinutes} min</dd>
        </div>
        <div>
          <dt><i className="swatch swatch--plain" />Scheduled close</dt>
          <dd>{formatDateTime(scheduledClose, now)}</dd>
        </div>
        {!preview && (
          <div>
            <dt><i className="swatch swatch--extension" />Current close</dt>
            <dd>
              {formatDateTime(currentClose, now)}
              {extendedBy > 0 && <span className="track__delta"> +{formatMinutes(extendedBy)}</span>}
            </dd>
          </div>
        )}
        <div>
          <dt><i className="swatch swatch--headroom" />Room to extend</dt>
          <dd>{roomLeft > 0 ? formatMinutes(roomLeft) : 'None left'}</dd>
        </div>
        <div>
          <dt><i className="swatch swatch--wall" />Forced close</dt>
          <dd>{formatDateTime(forcedClose, now)}</dd>
        </div>
      </dl>
    </figure>
  );
}
