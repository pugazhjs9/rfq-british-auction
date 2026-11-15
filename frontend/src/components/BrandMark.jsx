/** The favicon's drawing: bidding (amber) runs into the forced-close wall (red). */
export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="0.75" y="0.75" width="14.5" height="14.5" rx="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect x="3" y="7" width="7" height="2" fill="var(--signal)" />
      <rect x="11" y="4" width="2" height="8" fill="var(--stop)" />
    </svg>
  );
}
