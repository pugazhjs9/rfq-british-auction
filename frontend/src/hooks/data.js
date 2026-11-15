import { useCallback, useEffect, useRef, useState } from 'react';

/** Load data and expose `reload`. Late responses from older requests are ignored. */
export function useResource(load, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const loadRef = useRef(load);
  loadRef.current = load;
  const latest = useRef(0);

  const reload = useCallback(async () => {
    const request = ++latest.current;
    try {
      const data = await loadRef.current();
      if (request === latest.current) setState({ data, error: null, loading: false });
    } catch (error) {
      if (request === latest.current) setState((s) => ({ data: s.data, error, loading: false }));
    }
  }, []);

  useEffect(() => {
    setState({ data: null, error: null, loading: true });
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload };
}

export function usePolling(callback, intervalMs) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    const id = setInterval(() => saved.current(), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}

/**
 * Subscribe to a WebSocket feed and call `onMessage` for each update.
 * Reconnects with exponential backoff. Returns whether the socket is open,
 * so callers can poll more often while it is down.
 */
export function useLiveFeed(path, onMessage) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    let socket;
    let retryTimer;
    let attempt = 0;
    let stopped = false;

    function connect() {
      const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${scheme}//${window.location.host}${path}`);
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        try {
          handler.current(JSON.parse(event.data));
        } catch {
          // Ignore malformed messages; the next poll catches up.
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15_000));
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [path]);

  return connected;
}
