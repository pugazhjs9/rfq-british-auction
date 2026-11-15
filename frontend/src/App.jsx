import { Link, Route, Routes } from 'react-router-dom';
import { BrandMark } from './components/BrandMark.jsx';
import { ActingUserProvider, useActingUser } from './hooks/actingUser.jsx';
import { ServerClockProvider } from './hooks/serverClock.jsx';
import { monogram } from './lib/auction.js';
import AuctionDetail from './pages/AuctionDetail.jsx';
import AuctionList from './pages/AuctionList.jsx';
import CreateRfq from './pages/CreateRfq.jsx';
import SignIn from './pages/SignIn.jsx';

export default function App() {
  return (
    <ServerClockProvider>
      <ActingUserProvider>
        <Shell />
      </ActingUserProvider>
    </ServerClockProvider>
  );
}

function Shell() {
  const { user, loaded, error } = useActingUser();
  // Render nothing for the moment it takes to check a remembered account.
  if (!loaded && !error) return null;
  if (!user) return <SignIn />;

  return (
    <>
      <TopBar user={user} />
      <main className="page">
        <Routes>
          <Route path="/" element={<AuctionList />} />
          <Route path="/rfqs/new" element={<CreateRfq />} />
          <Route path="/rfqs/:id" element={<AuctionDetail />} />
          <Route
            path="*"
            element={
              <div className="page-message">
                <h1>Page not found</h1>
                <Link to="/" className="button">Back to auctions</Link>
              </div>
            }
          />
        </Routes>
      </main>
    </>
  );
}

function TopBar({ user }) {
  const { signOut } = useActingUser();
  return (
    <header className="topbar">
      <Link to="/" className="topbar__brand">
        <BrandMark />
        RFQ Auctions
      </Link>
      <div className="topbar__account">
        <span className={`monogram monogram--${user.role.toLowerCase()}`} aria-hidden="true">
          {monogram(user.company)}
        </span>
        <span className="topbar__who">
          <span className="topbar__company">{user.company}</span>
          <span className="topbar__role">{user.role === 'BUYER' ? 'Buyer' : 'Supplier'}</span>
        </span>
        {/* Signing out keeps the URL, so you come back to the same page as someone else. */}
        <button type="button" className="topbar__switch" onClick={signOut}>
          Switch account
        </button>
      </div>
    </header>
  );
}
