import { STATUS_LABEL } from '../lib/auction.js';

export function StatusBadge({ status }) {
  return <span className={`status status--${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>;
}
