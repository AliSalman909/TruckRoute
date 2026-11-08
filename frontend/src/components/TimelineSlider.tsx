import { useEffect, useMemo, useState } from 'react';
import { formatDayTime } from '../lib/format';
import { METRICS, metricGradientCss } from '../lib/risk';
import { useAppStore, useSelectedRoute } from '../store/useAppStore';
import type { HeatmapMetric } from '../types';

const MAX_HOURS = 48;
const TICKS = [0, 6, 12, 18, 24, 30, 36, 42, 48];
const PLAY_INTERVAL_MS = 650;

/** 0-48 h scrubber driving the heatmap hour and the simulated truck position. */
export function TimelineSlider() {
  const analysis = useAppStore((s) => s.analysis);
  const grid = useAppStore((s) => s.grid);
  const gridStatus = useAppStore((s) => s.gridStatus);
  const gridError = useAppStore((s) => s.gridError);
  const offset = useAppStore((s) => s.forecastHourOffset);
  const setOffset = useAppStore((s) => s.setForecastHourOffset);
  const metric = useAppStore((s) => s.heatmapMetric);
  const setMetric = useAppStore((s) => s.setHeatmapMetric);
  const visible = useAppStore((s) => s.heatmapVisible);
  const toggleHeatmap = useAppStore((s) => s.toggleHeatmap);
  const route = useSelectedRoute();
  const [playing, setPlaying] = useState(false);

  const maxHour = grid ? Math.min(MAX_HOURS, grid.times.length - 1) : MAX_HOURS;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const next = useAppStore.getState().forecastHourOffset + 1;
      if (next > maxHour) {
        setPlaying(false);
      } else {
        setOffset(next);
      }
    }, PLAY_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [playing, maxHour, setOffset]);

  useEffect(() => setPlaying(false), [analysis]);

  const baseIso = grid?.start_time ?? analysis?.request.departure_time;
  const currentIso = useMemo(
    () => (baseIso ? new Date(Date.parse(baseIso) + offset * 3_600_000).toISOString() : null),
    [baseIso, offset],
  );

  // Band on the track showing when the selected route is on the road.
  const tripBand = useMemo(() => {
    if (!route || !baseIso) return null;
    const startH = (Date.parse(route.departure_time) - Date.parse(baseIso)) / 3_600_000;
    const endH = (Date.parse(route.arrival_time) - Date.parse(baseIso)) / 3_600_000;
    const left = Math.max(0, startH / MAX_HOURS) * 100;
    const right = Math.min(1, endH / MAX_HOURS) * 100;
    return { left, width: Math.max(0, right - left) };
  }, [route, baseIso]);

  if (!analysis) return null;

  const togglePlay = () => {
    if (!playing && offset >= maxHour) setOffset(0);
    setPlaying((p) => !p);
  };

  return (
    <section className="timeline" aria-label="Forecast timeline">
      <div className="timeline__top">
        <button
          type="button"
          className="icon-btn icon-btn--primary"
          onClick={togglePlay}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
        >
          {playing ? (
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <rect x="3" y="2" width="3.5" height="12" rx="1" fill="currentColor" />
              <rect x="9.5" y="2" width="3.5" height="12" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path d="M4 2.5v11l9.5-5.5z" fill="currentColor" />
            </svg>
          )}
        </button>
        <div className="timeline__time">
          <span className="timeline__offset">T+{offset}h</span>
          <span className="timeline__clock">{currentIso ? formatDayTime(currentIso) : '—'}</span>
        </div>

        <div className="timeline__controls">
          <div className="segmented segmented--sm" role="radiogroup" aria-label="Heatmap layer">
            {(Object.keys(METRICS) as HeatmapMetric[]).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={metric === m}
                className={metric === m ? 'is-active' : ''}
                onClick={() => setMetric(m)}
              >
                {METRICS[m].label}
              </button>
            ))}
          </div>
          <label className="switch">
            <input type="checkbox" checked={visible} onChange={toggleHeatmap} />
            <span className="switch__track" aria-hidden="true" />
            <span className="switch__label">Heatmap</span>
          </label>
        </div>
      </div>

      <div className="timeline__track">
        {tripBand && (
          <div
            className="timeline__band"
            style={{ left: `${tripBand.left}%`, width: `${tripBand.width}%` }}
            title="Selected route on the road"
          />
        )}
        <input
          type="range"
          min={0}
          max={MAX_HOURS}
          step={1}
          value={offset}
          onChange={(e) => {
            setPlaying(false);
            setOffset(Math.min(maxHour, Number(e.target.value)));
          }}
          aria-label="Hours after departure"
          aria-valuetext={currentIso ? `${offset} hours after departure, ${formatDayTime(currentIso)}` : undefined}
        />
      </div>
      <div className="timeline__ticks" aria-hidden="true">
        {TICKS.map((t) => (
          <span key={t} style={{ left: `${(t / MAX_HOURS) * 100}%` }}>
            {t}h
          </span>
        ))}
      </div>

      <div className="timeline__footer">
        <div className="scale">
          <span className="scale__label">{METRICS[metric].label}</span>
          <span className="scale__bar" style={{ background: metricGradientCss(metric) }} />
          <span className="scale__ends">
            <span>{METRICS[metric].format(METRICS[metric].legend[0])}</span>
            <span>{METRICS[metric].format(METRICS[metric].legend[1])}</span>
          </span>
        </div>
        <span className="timeline__status">
          {gridStatus === 'loading' && 'Loading corridor forecast…'}
          {gridStatus === 'error' && <span className="text-danger">Heatmap unavailable: {gridError}</span>}
          {gridStatus === 'success' && tripBand && <span><span className="band-key" /> On the road</span>}
        </span>
      </div>
    </section>
  );
}
