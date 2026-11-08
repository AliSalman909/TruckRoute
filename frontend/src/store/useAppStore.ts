import { create } from 'zustand';
import type { ApiError } from '../api/client';
import { nextFullHour, toLocalInputValue } from '../lib/format';
import type { AnalyzeResponse, HeatmapMetric, IntervalMiles, LatLng, WeatherGridResponse } from '../types';

export interface FormValues {
  origin: string;
  destination: string;
  /** Coordinates of a picked suggestion; cleared as soon as the text is edited. */
  originLocation: LatLng | null;
  destinationLocation: LatLng | null;
  departureLocal: string; // datetime-local value, browser time zone
  loadWeight: string;
  intervalMiles: IntervalMiles;
}

type Status = 'idle' | 'loading' | 'success' | 'error';

export interface CheckpointRef {
  routeId: string;
  sequence: number;
}

interface AppState {
  form: FormValues;
  analysis: AnalyzeResponse | null;
  status: Status;
  error: ApiError | null;

  selectedRouteId: string | null;
  activeCheckpoint: CheckpointRef | null;
  hoveredCheckpoint: CheckpointRef | null;

  grid: WeatherGridResponse | null;
  gridStatus: Status;
  gridError: string | null;
  forecastHourOffset: number;
  heatmapMetric: HeatmapMetric;
  heatmapVisible: boolean;

  setForm: (patch: Partial<FormValues>) => void;
  startAnalysis: () => void;
  analysisSucceeded: (data: AnalyzeResponse) => void;
  analysisFailed: (error: ApiError) => void;
  selectRoute: (id: string) => void;
  setActiveCheckpoint: (ref: CheckpointRef | null) => void;
  setHoveredCheckpoint: (ref: CheckpointRef | null) => void;
  setGridState: (patch: Partial<Pick<AppState, 'grid' | 'gridStatus' | 'gridError'>>) => void;
  setForecastHourOffset: (h: number) => void;
  setHeatmapMetric: (m: HeatmapMetric) => void;
  toggleHeatmap: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  form: {
    origin: 'Chicago, IL, USA',
    destination: 'Denver, CO, USA',
    originLocation: null,
    destinationLocation: null,
    departureLocal: toLocalInputValue(nextFullHour()),
    loadWeight: '45000',
    intervalMiles: 25,
  },
  analysis: null,
  status: 'idle',
  error: null,
  selectedRouteId: null,
  activeCheckpoint: null,
  hoveredCheckpoint: null,
  grid: null,
  gridStatus: 'idle',
  gridError: null,
  forecastHourOffset: 0,
  heatmapMetric: 'risk',
  heatmapVisible: true,

  setForm: (patch) => set((s) => ({ form: { ...s.form, ...patch } })),
  startAnalysis: () => set({ status: 'loading', error: null, activeCheckpoint: null }),
  analysisSucceeded: (data) =>
    set({
      analysis: data,
      status: 'success',
      error: null,
      selectedRouteId: data.recommended_route_id,
      activeCheckpoint: null,
      grid: null,
      gridStatus: 'idle',
      gridError: null,
      forecastHourOffset: 0,
    }),
  analysisFailed: (error) => set({ status: 'error', error }),
  selectRoute: (id) =>
    set((s) => (s.selectedRouteId === id ? s : { selectedRouteId: id, activeCheckpoint: null })),
  setActiveCheckpoint: (ref) => set({ activeCheckpoint: ref }),
  setHoveredCheckpoint: (ref) => set({ hoveredCheckpoint: ref }),
  setGridState: (patch) => set(patch),
  setForecastHourOffset: (h) => set({ forecastHourOffset: h }),
  setHeatmapMetric: (m) => set({ heatmapMetric: m }),
  toggleHeatmap: () => set((s) => ({ heatmapVisible: !s.heatmapVisible })),
}));

// Dev-only handle for debugging and browser automation (stripped from production builds).
if (import.meta.env.DEV) (window as unknown as { __safehaul: typeof useAppStore }).__safehaul = useAppStore;

export const useSelectedRoute = () =>
  useAppStore((s) => s.analysis?.routes.find((r) => r.id === s.selectedRouteId) ?? null);
