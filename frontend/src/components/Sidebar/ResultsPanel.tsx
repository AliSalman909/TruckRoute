import { useEffect, useState } from 'react';
import { useRoutingAPI } from '../../hooks/useRoutingAPI';
import { formatDayTime, formatFull, formatLb, routeLetter, toLocalInputValue } from '../../lib/format';
import { useAppStore } from '../../store/useAppStore';
import type { ResolvedPlace } from '../../types';
import { RouteList } from './RouteList';

export function ResultsPanel() {
  const status = useAppStore((s) => s.status);
  const error = useAppStore((s) => s.error);
  const hasAnalysis = useAppStore((s) => !!s.analysis);

  return (
    <div className="results" aria-live="polite">
      {status === 'error' && error && (
        <div className="alert alert--danger" role="alert">
          <strong>Couldn’t analyze this trip.</strong> {error.message}
        </div>
      )}
      {status === 'loading' && <LoadingState />}
      {status !== 'loading' && hasAnalysis && (
        <>
          <TripSummary />
          <SafetyBanner />
          <RouteList />
        </>
      )}
      {status === 'idle' && !hasAnalysis && <EmptyState />}
    </div>
  );
}

function TripSummary() {
  const analysis = useAppStore((s) => s.analysis)!;
  const { request, origin, destination } = analysis;
  return (
    <div className="trip-summary">
      <dl className="resolved">
        <ResolvedRow letter="A" role="From" place={origin} />
        <ResolvedRow letter="B" role="To" place={destination} />
      </dl>
      <div className="trip-summary__meta">
        Departs {formatFull(request.departure_time)} · {formatLb(request.load_weight)} · every{' '}
        {request.interval_miles} mi
      </div>
    </div>
  );
}

const MATCH_TEXT: Record<ResolvedPlace['matched_by'], string> = {
  suggestion: 'Selected from suggestions',
  coordinates: 'From coordinates',
  search: 'Best match',
};

/** "We understood 'Springfield' as Springfield, MO, USA". Best guesses get a nudge to check. */
function ResolvedRow({ letter, role, place }: { letter: string; role: string; place: ResolvedPlace }) {
  const guessed = place.matched_by === 'search' && place.query.trim().toLowerCase() !== place.label.toLowerCase();
  return (
    <div className={`resolved__row${guessed ? ' is-guess' : ''}`}>
      <dt>
        <span className={`od__pin od__pin--${letter.toLowerCase()}`} aria-hidden="true">
          {letter}
        </span>
        <span className="visually-hidden">{role}</span>
      </dt>
      <dd>
        <span className="resolved__label">{place.label}</span>
        <span className="resolved__how">
          {guessed ? (
            <>
              Best match for “{place.query}”. Not right? Pick the exact place from the suggestions.
            </>
          ) : (
            MATCH_TEXT[place.matched_by]
          )}
        </span>
      </dd>
    </div>
  );
}

function SafetyBanner() {
  const analysis = useAppStore((s) => s.analysis)!;
  const form = useAppStore((s) => s.form);
  const setForm = useAppStore((s) => s.setForm);
  const { analyze } = useRoutingAPI();
  const safe = analysis.safe_departure;
  const letterOf = (id: string) => routeLetter(analysis.routes.findIndex((r) => r.id === id));

  const rerun = () => {
    if (!safe) return;
    const next = { ...form, departureLocal: toLocalInputValue(new Date(safe.departure_time)) };
    setForm(next);
    analyze(next);
  };

  return (
    <>
      {analysis.all_routes_unsafe && (
        <div className="alert alert--blocked" role="alert">
          <div className="alert__title">No route is safe at this departure time</div>
          {safe ? (
            <>
              <p>
                Leaving <strong>{safe.delay_hours} h later</strong> ({formatDayTime(safe.departure_time)}) clears
                Route {letterOf(safe.route_id)} of No Travel conditions.
              </p>
              <button type="button" className="btn btn--light" onClick={rerun}>
                Re-analyze for {formatDayTime(safe.departure_time)}
              </button>
            </>
          ) : (
            <p>Conditions stay unsafe for at least the next day on every route. Consider postponing the trip.</p>
          )}
        </div>
      )}
      {analysis.warnings.map((w) => (
        <div key={w} className="alert alert--warn">
          {w}
        </div>
      ))}
      <p className="provider-note">
        Routes from FreeRoute (car profile; travel times adjusted for a truck). Check truck restrictions locally.
      </p>
    </>
  );
}

const STEPS = ['Finding route options', 'Placing checkpoints', 'Fetching forecasts at each ETA', 'Scoring risk'];

function LoadingState() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1400);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="loading">
      <ol className="steps">
        {STEPS.map((label, i) => (
          <li key={label} className={i < step ? 'is-done' : i === step ? 'is-current' : ''}>
            <span className="steps__dot" aria-hidden="true" />
            {label}
          </li>
        ))}
      </ol>
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton-card" aria-hidden="true">
          <span className="skeleton skeleton--title" />
          <span className="skeleton skeleton--line" />
          <span className="skeleton skeleton--bar" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <h2 className="section-title">How it works</h2>
      <ol className="how">
        <li>
          <strong>Three routes.</strong> Alternatives from the routing provider, plus generated detours if fewer than
          three exist.
        </li>
        <li>
          <strong>Weather at your ETA.</strong> Forecast sampled every 10, 25 or 50 miles for the hour the truck
          actually gets there.
        </li>
        <li>
          <strong>Load-aware risk.</strong> Wind, rain and snow thresholds tighten for loads over 30,000 and 40,000 lb.
        </li>
        <li>
          <strong>Safest first.</strong> Fewest Severe miles, then High miles, average risk, and travel time.
        </li>
      </ol>
    </div>
  );
}
