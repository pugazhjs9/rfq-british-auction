import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api.js';
import { toMs } from '../lib/format.js';

const ClockContext = createContext({ now: Date.now(), offset: 0 });

/**
 * Countdowns use the server's clock, not the browser's. The offset is measured
 * the way NTP does it: assume the server read its clock halfway through the
 * round trip.
 */
export function ServerClockProvider({ children }) {
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    async function sync() {
      try {
        const sent = Date.now();
        const { now } = await api.time();
        const received = Date.now();
        if (!cancelled) setOffset(toMs(now) - (sent + received) / 2);
      } catch {
        // Keep the last offset; countdowns fall back to the browser clock.
      }
    }
    sync();
    const resync = setInterval(sync, 5 * 60_000);
    const ticker = setInterval(() => setTick(Date.now()), 250);
    return () => {
      cancelled = true;
      clearInterval(resync);
      clearInterval(ticker);
    };
  }, []);

  const value = useMemo(() => ({ now: tick + offset, offset }), [tick, offset]);
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>;
}

export const useNow = () => useContext(ClockContext).now;
export const useClockOffset = () => useContext(ClockContext).offset;
