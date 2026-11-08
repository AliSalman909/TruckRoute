import { useCallback, useRef } from 'react';
import { api, toApiError } from '../api/client';
import { useAppStore, type FormValues } from '../store/useAppStore';
import type { AnalyzeRequest, AnalyzeResponse } from '../types';

export function toRequest(form: FormValues): AnalyzeRequest {
  return {
    origin: form.origin.trim(),
    destination: form.destination.trim(),
    departure_time: new Date(form.departureLocal).toISOString(),
    load_weight: Number(form.loadWeight),
    interval_miles: form.intervalMiles,
    origin_location: form.originLocation,
    destination_location: form.destinationLocation,
  };
}

/** POST /analyze-routes/. A new submission cancels the one in flight. */
export function useRoutingAPI() {
  const controller = useRef<AbortController | null>(null);
  const { startAnalysis, analysisSucceeded, analysisFailed } = useAppStore.getState();

  const analyze = useCallback(async (form: FormValues) => {
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    startAnalysis();
    try {
      const { data } = await api.post<AnalyzeResponse>('/analyze-routes/', toRequest(form), {
        signal: ctrl.signal,
      });
      if (!ctrl.signal.aborted) analysisSucceeded(data);
    } catch (err) {
      if (!ctrl.signal.aborted) analysisFailed(toApiError(err));
    }
  }, [startAnalysis, analysisSucceeded, analysisFailed]);

  return { analyze };
}
