import { useState, type FormEvent } from 'react';
import { useRoutingAPI } from '../../hooks/useRoutingAPI';
import { toLocalInputValue } from '../../lib/format';
import { useAppStore } from '../../store/useAppStore';
import type { IntervalMiles } from '../../types';
import { PlaceInput } from './PlaceInput';

const INTERVALS: IntervalMiles[] = [10, 25, 50];
const MAX_DAYS_AHEAD = 14;
// Stable fallback: a fresh `{}` in a zustand selector re-renders forever.
const NO_ERRORS: Record<string, string> = {};

function loadHint(lb: number): string {
  if (!Number.isFinite(lb) || lb <= 0) return 'Wind limits depend on load weight.';
  if (lb > 40_000) return 'Heavy load: wind ≥35 mph is Severe, ≥45 mph is No Travel.';
  if (lb > 30_000) return 'Wind ≥45 mph is No Travel at this weight.';
  return 'Standard wind limits apply (No Travel at ≥55 mph).';
}

export function InputForm() {
  const form = useAppStore((s) => s.form);
  const setForm = useAppStore((s) => s.setForm);
  const loading = useAppStore((s) => s.status === 'loading');
  const serverErrors = useAppStore((s) => s.error?.fieldErrors ?? NO_ERRORS);
  const { analyze } = useRoutingAPI();
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const errors = { ...serverErrors, ...localErrors };
  const now = new Date();
  const maxDate = new Date(now.getTime() + MAX_DAYS_AHEAD * 86_400_000);

  const validate = (): Record<string, string> => {
    const e: Record<string, string> = {};
    if (!form.origin.trim()) e.origin = 'Enter an origin.';
    if (!form.destination.trim()) e.destination = 'Enter a destination.';
    const weight = Number(form.loadWeight);
    if (form.loadWeight === '' || !Number.isFinite(weight) || weight < 0) e.load_weight = 'Enter a load weight in pounds.';
    else if (weight > 120_000) e.load_weight = 'Load weight must be 120,000 lb or less.';
    const dep = new Date(form.departureLocal);
    if (Number.isNaN(dep.getTime())) e.departure_time = 'Choose a departure time.';
    return e;
  };

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    const e = validate();
    setLocalErrors(e);
    if (Object.keys(e).length === 0) analyze(form);
  };

  const swap = () =>
    setForm({
      origin: form.destination,
      destination: form.origin,
      originLocation: form.destinationLocation,
      destinationLocation: form.originLocation,
    });

  return (
    <form className="trip-form" onSubmit={onSubmit} noValidate>
      <div className="od">
        <div className="od__rail" aria-hidden="true">
          <span className="od__pin od__pin--a">A</span>
          <span className="od__line" />
          <span className="od__pin od__pin--b">B</span>
        </div>
        <div className="od__fields">
          <Field label="Origin" error={errors.origin} htmlFor="origin">
            <PlaceInput
              id="origin"
              value={form.origin}
              location={form.originLocation}
              invalid={!!errors.origin}
              placeholder="City, address or lat,lng"
              onChange={(origin, originLocation) => setForm({ origin, originLocation })}
            />
          </Field>
          <Field label="Destination" error={errors.destination} htmlFor="destination">
            <PlaceInput
              id="destination"
              value={form.destination}
              location={form.destinationLocation}
              invalid={!!errors.destination}
              placeholder="City, address or lat,lng"
              onChange={(destination, destinationLocation) => setForm({ destination, destinationLocation })}
            />
          </Field>
        </div>
        <button type="button" className="icon-btn od__swap" onClick={swap} aria-label="Swap origin and destination">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M5 2v10M5 12l-2.5-2.5M5 12l2.5-2.5M11 14V4M11 4L8.5 6.5M11 4l2.5 2.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <p className="hint hint--od">US locations only. Pick from the suggestions for an exact match.</p>

      <div className="form-row">
        <Field label="Departure" error={errors.departure_time} htmlFor="departure">
          <input
            id="departure"
            type="datetime-local"
            value={form.departureLocal}
            min={toLocalInputValue(now)}
            max={toLocalInputValue(maxDate)}
            onChange={(e) => setForm({ departureLocal: e.target.value })}
          />
        </Field>
        <Field label="Load weight" error={errors.load_weight} htmlFor="load">
          <div className="input-suffix">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min={0}
              max={120000}
              step={500}
              value={form.loadWeight}
              onChange={(e) => setForm({ loadWeight: e.target.value })}
            />
            <span>lb</span>
          </div>
        </Field>
      </div>
      <p className="hint">{loadHint(Number(form.loadWeight))}</p>

      <fieldset className="field">
        <legend className="field__label">Check weather every</legend>
        <div className="segmented" role="radiogroup">
          {INTERVALS.map((mi) => (
            <button
              key={mi}
              type="button"
              role="radio"
              aria-checked={form.intervalMiles === mi}
              className={form.intervalMiles === mi ? 'is-active' : ''}
              onClick={() => setForm({ intervalMiles: mi })}
            >
              {mi} mi
            </button>
          ))}
        </div>
      </fieldset>

      <button type="submit" className="btn btn--primary btn--block" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" aria-hidden="true" /> Analyzing routes…
          </>
        ) : (
          'Find the safest route'
        )}
      </button>
    </form>
  );
}

function Field({
  label,
  error,
  htmlFor,
  children,
}: {
  label: string;
  error?: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`field${error ? ' has-error' : ''}`}>
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error && (
        <span className="field__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
