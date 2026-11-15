import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api.js';

const STORAGE_KEY = 'rfq-auctions.acting-user';
const ActingUserContext = createContext(null);

function readStoredId() {
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

function storeId(id) {
  try {
    if (id == null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    // Not remembering the choice is fine.
  }
}

/**
 * Mock sign-in: pick which buyer or supplier you are acting as. The API trusts
 * the X-User-Id header; a real deployment would use verified tokens.
 */
export function ActingUserProvider({ children }) {
  const [users, setUsers] = useState(null); // null until loaded
  const [error, setError] = useState(null);
  const [userId, setUserId] = useState(readStoredId);

  const loadUsers = useCallback(() => {
    setError(null);
    api.users().then(setUsers, setError);
  }, []);

  useEffect(loadUsers, [loadUsers]);

  const signIn = useCallback((id) => {
    setUserId(id);
    storeId(id);
  }, []);

  const signOut = useCallback(() => {
    setUserId(null);
    storeId(null);
  }, []);

  const value = useMemo(
    () => ({
      users: users ?? [],
      loaded: users !== null,
      error,
      retry: loadUsers,
      // A remembered id that no longer exists (e.g. after a reseed) means signed out.
      user: users?.find((u) => u.id === userId) ?? null,
      signIn,
      signOut,
    }),
    [users, error, loadUsers, userId, signIn, signOut],
  );

  return <ActingUserContext.Provider value={value}>{children}</ActingUserContext.Provider>;
}

export const useActingUser = () => useContext(ActingUserContext);
