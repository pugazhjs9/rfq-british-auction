const MINUTE = 60_000;

/** ISO string -> epoch ms. Trims microseconds, which not every browser parses. */
export const toMs = (iso) => Date.parse(iso.replace(/(\.\d{3})\d+/, '$1'));

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const inrPaise = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });

export function formatMoney(value) {
  if (value == null || value === '') return '';
  const amount = Number(value);
  return Number.isInteger(amount) ? inr.format(amount) : inrPaise.format(amount);
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const timeSecFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const dayFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });
const dateFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

const asDate = (value) => (typeof value === 'number' ? new Date(value) : new Date(toMs(value)));
const sameDay = (a, b) => a.toDateString() === b.toDateString();

export const formatTime = (value, { seconds = false } = {}) =>
  (seconds ? timeSecFmt : timeFmt).format(asDate(value));

/** "18:05" today, "14 Nov, 18:05" any other day. */
export function formatDateTime(value, now = Date.now(), options) {
  const date = asDate(value);
  const time = formatTime(date.getTime(), options);
  return sameDay(date, new Date(now)) ? time : `${dayFmt.format(date)}, ${time}`;
}

/** "13 Nov" when `value` falls on a different day than `now`, otherwise null. */
export function otherDay(value, now = Date.now()) {
  const date = asDate(value);
  return sameDay(date, new Date(now)) ? null : dayFmt.format(date);
}

/** A plain "YYYY-MM-DD" date, shown without shifting it through a time zone. */
export function formatDate(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
}

/** Like formatDate, but leaves out the year when it's the current one. */
export function formatShortDate(isoDate, now = Date.now()) {
  const [y, m, d] = isoDate.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return y === new Date(now).getFullYear() ? dayFmt.format(date) : dateFmt.format(date);
}

/** 4:05, 1:04:05, or 2 d 4 h for long waits. */
export function formatCountdown(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (days > 0) return `${days} d ${hours} h`;
  const ss = String(seconds).padStart(2, '0');
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${ss}`;
  return `${minutes}:${ss}`;
}

export function formatMinutes(ms) {
  const minutes = Math.round(ms / MINUTE);
  return `${minutes} min`;
}

/** 45 min, 2 h, 2 h 5 min */
export function formatSpan(ms) {
  const minutes = Math.round(ms / MINUTE);
  const hours = Math.floor(minutes / 60);
  if (hours === 0) return `${minutes} min`;
  return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
}

export function timeZoneLabel() {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const offset = -new Date().getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const hh = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0');
  const mm = String(Math.abs(offset) % 60).padStart(2, '0');
  return `${zone} (UTC${sign}${hh}:${mm})`;
}

/** epoch ms -> value for <input type="datetime-local"> in local time. */
export function toLocalInput(ms) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function toLocalDate(ms) {
  return toLocalInput(ms).slice(0, 10);
}
