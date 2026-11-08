import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { PlaceSuggestion, PlacesResponse } from '../types';

const DEBOUNCE_MS = 250;
const MIN_CHARS = 2;

/**
 * Suggestions for a place input. Waits until typing pauses (debounce) so we don't
 * call the API on every keystroke, and cancels a request that's been overtaken.
 */
export function usePlaceSuggestions(query: string, enabled: boolean) {
  const [results, setResults] = useState<PlaceSuggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (!enabled || q.length < MIN_CHARS) {
      setResults([]);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api
        .get<PlacesResponse>('/places/', { params: { q, limit: 6 }, signal: ctrl.signal })
        .then(({ data }) => setResults(data.results))
        .catch(() => {
          if (!ctrl.signal.aborted) setResults([]); // suggestions are optional; typing still works
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [query, enabled]);

  return { results, loading };
}
