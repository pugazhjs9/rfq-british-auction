import { inTriggerWindow } from '../lib/auction.js';
import { formatCountdown, formatDateTime, formatTime, otherDay, toMs } from '../lib/format.js';

export function Countdown({ rfq, status, now, flash }) {
  const close = toMs(rfq.current_close_at);
  const start = toMs(rfq.bid_start_at);

  const closedDay = otherDay(close, now);
  const on = closedDay ? `On ${closedDay}. ` : '';
  let label;
  let value;
  let note;
  let tone = '';
  switch (status) {
    case 'UPCOMING':
      label = 'Opens in';
      value = formatCountdown(start - now);
      note = `Bidding opens at ${formatDateTime(start, now)}`;
      break;
    case 'ACTIVE':
      label = 'Closes in';
      value = formatCountdown(close - now);
      if (inTriggerWindow(now, rfq)) {
        tone = 'countdown--window';
        note = `Trigger window open: a qualifying bid adds ${rfq.extension_minutes} min`;
      } else {
        note = `at ${formatDateTime(close, now, { seconds: true })}`;
      }
      break;
    case 'FORCE_CLOSED':
      label = 'Force-closed at';
      value = formatTime(close);
      note = `${on}Extensions ran up to the forced close time`;
      tone = 'countdown--forced';
      break;
    default:
      label = 'Closed at';
      value = formatTime(close);
      note = `${on}Bidding has ended`;
  }

  return (
    <div className={`countdown ${tone} ${flash ? 'countdown--flash' : ''}`} role="timer" aria-live="off">
      <p className="countdown__label">{label}</p>
      <p className="countdown__value">{value}</p>
      <p className="countdown__note">{note}</p>
    </div>
  );
}
