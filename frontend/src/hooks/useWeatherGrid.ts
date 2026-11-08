import { useEffect } from 'react';
import { api, toApiError } from '../api/client';
import { useAppStore } from '../store/useAppStore';
import type { WeatherGridResponse } from '../types';

/**
 * Fetches the 0-48 h corridor weather grid once per analysis. The timeline
 * slider then only re-slices this data locally; it makes no further API calls.
 */
export function useWeatherGrid() {
  const analysis = useAppStore((s) => s.analysis);
  const setGridState = useAppStore((s) => s.setGridState);

  useEffect(() => {
    if (!analysis) return;
    const ctrl = new AbortController();
    setGridState({ gridStatus: 'loading', gridError: null });
    api
      .post<WeatherGridResponse>(
        '/weather-grid/',
        {
          polylines: analysis.routes.map((r) => r.encoded_polyline),
          start_time: analysis.request.departure_time,
          load_weight: analysis.request.load_weight,
          hours: 48,
        },
        { signal: ctrl.signal },
      )
      .then(({ data }) => setGridState({ grid: data, gridStatus: 'success' }))
      .catch((err) => {
        if (!ctrl.signal.aborted) setGridState({ gridStatus: 'error', gridError: toApiError(err).message });
      });
    return () => ctrl.abort();
  }, [analysis, setGridState]);
}
