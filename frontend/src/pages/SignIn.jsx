import { BrandMark } from '../components/BrandMark.jsx';
import { useActingUser } from '../hooks/actingUser.jsx';
import { monogram } from '../lib/auction.js';

const ROLE_COPY = {
  BUYER: 'Creates RFQs and sees every bid by name.',
  SUPPLIER: 'Bids on open RFQs. Competitors stay anonymous.',
};

/** Shown instead of the app until an account is chosen. The URL is kept, so deep links still land. */
export default function SignIn() {
  const { users, loaded, error, retry, signIn } = useActingUser();
  const buyers = users.filter((u) => u.role === 'BUYER');
  const suppliers = users.filter((u) => u.role === 'SUPPLIER');

  return (
    <div className="signin">
      <header className="signin__hero">
        <div className="signin__inner">
          <p className="signin__brand">
            <BrandMark />
            RFQ Auctions
          </p>
          <h1>Freight quotes, bid down in the open.</h1>
          <p className="signin__lede">
            Suppliers undercut each other live. A late bid extends the close, but never past the forced close time.
          </p>
          <div className="signin__motif" aria-hidden="true">
            <span className="signin__motif-bidding" />
            <span className="signin__motif-extension" />
            <span className="signin__motif-extension" />
            <span className="signin__motif-headroom" />
          </div>
        </div>
      </header>

      <main className="signin__inner signin__main">
        <h2>Choose an account</h2>
        <p className="muted">
          This demo has no passwords. You can switch accounts at any time from the top bar.
        </p>

        {error && (
          <div className="notice notice--error signin__error">
            Couldn't load the accounts: {error.message}.{' '}
            <button type="button" className="linkish" onClick={retry}>
              Try again
            </button>
          </div>
        )}
        {!loaded && !error && <p className="muted">Loading accounts…</p>}

        {loaded && (
          <>
            <AccountGroup title="Buyer" users={buyers} onPick={signIn} />
            <AccountGroup title="Suppliers" users={suppliers} onPick={signIn} />
          </>
        )}
      </main>
    </div>
  );
}

function AccountGroup({ title, users, onPick }) {
  if (users.length === 0) return null;
  return (
    <section className="accounts" aria-label={title}>
      <h3>{title}</h3>
      <ul className="accounts__list">
        {users.map((u) => (
          <li key={u.id}>
            <button type="button" className="account" onClick={() => onPick(u.id)}>
              <span className={`monogram monogram--${u.role.toLowerCase()}`} aria-hidden="true">
                {monogram(u.company)}
              </span>
              <span className="account__text">
                <span className="account__company">{u.company}</span>
                <span className="account__person">{u.name}</span>
                <span className="account__role">{ROLE_COPY[u.role]}</span>
              </span>
              <span className="account__go" aria-hidden="true">›</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
