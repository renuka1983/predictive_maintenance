import { useCallback, useEffect, useRef, useState } from 'react';
import { FeatureLockedError } from '../api/client';

/**
 * Run an async API call and expose {data, error, locked, loading, reload}.
 *
 * A 403 from the feature gate is surfaced separately as `locked` so callers
 * can render an upgrade prompt instead of an error.
 */
export function useApi(fetcher, deps = [], { enabled = true, pollMs = 0 } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [locked, setLocked] = useState(null);
  const [loading, setLoading] = useState(enabled);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(
    async (isBackground = false) => {
      if (!enabled) {
        setLoading(false);
        return;
      }
      if (!isBackground) setLoading(true);
      try {
        const result = await fetcherRef.current();
        setData(result);
        setError(null);
        setLocked(null);
      } catch (caught) {
        if (caught instanceof FeatureLockedError) {
          setLocked(caught);
          setError(null);
        } else {
          setError(caught);
        }
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, ...deps],
  );

  useEffect(() => {
    run();
  }, [run]);

  useEffect(() => {
    if (!pollMs || !enabled) return undefined;
    // Background refreshes must not blank the page, so they skip the
    // loading state.
    const timer = setInterval(() => run(true), pollMs);
    return () => clearInterval(timer);
  }, [pollMs, enabled, run]);

  return { data, error, locked, loading, reload: () => run(false) };
}
