import { useEffect, useMemo } from 'react';
import { Marker, Popup, useMap } from 'react-map-gl/maplibre';
import { formatFull, formatMiles } from '../../lib/format';
import { cumulativeMiles, truckPositionAt } from '../../lib/geo';
import { RISK_KEY } from '../../lib/risk';
import { useAppStore, useSelectedRoute } from '../../store/useAppStore';
import type { Checkpoint } from '../../types';
import { RiskPill } from '../RiskPill';

/** Checkpoint dots for the selected route, plus a popup for the active one. */
export function CheckpointMarkers() {
  const { current: map } = useMap();
  const route = useSelectedRoute();
  const active = useAppStore((s) => s.activeCheckpoint);
  const hovered = useAppStore((s) => s.hoveredCheckpoint);
  const setActive = useAppStore((s) => s.setActiveCheckpoint);
  const setHovered = useAppStore((s) => s.setHoveredCheckpoint);

  const activeCp =
    route && active?.routeId === route.id ? route.checkpoints.find((c) => c.sequence === active.sequence) : undefined;

  useEffect(() => {
    if (map && activeCp) map.easeTo({ center: [activeCp.lng, activeCp.lat], duration: 500 });
  }, [map, activeCp]);

  if (!route) return null;
  return (
    <>
      {route.checkpoints.map((cp) => {
        const ref = { routeId: route.id, sequence: cp.sequence };
        const emphasised =
          activeCp?.sequence === cp.sequence || (hovered?.routeId === route.id && hovered.sequence === cp.sequence);
        return (
          <Marker
            key={`${route.id}-${cp.sequence}`}
            longitude={cp.lng}
            latitude={cp.lat}
            anchor="center"
            style={{ zIndex: emphasised ? 3 : 1 }}
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              setActive(ref);
            }}
          >
            <span
              className={`cp-dot risk-${RISK_KEY[cp.risk_level]}${emphasised ? ' is-emphasised' : ''}`}
              title={`Checkpoint ${cp.sequence} · ${cp.risk_level}`}
              onMouseEnter={() => setHovered(ref)}
              onMouseLeave={() => setHovered(null)}
            />
          </Marker>
        );
      })}
      {activeCp && (
        <Popup
          longitude={activeCp.lng}
          latitude={activeCp.lat}
          anchor="bottom"
          offset={12}
          maxWidth="300px"
          closeOnClick={false}
          onClose={() => setActive(null)}
        >
          <CheckpointDetails cp={activeCp} />
        </Popup>
      )}
    </>
  );
}

function CheckpointDetails({ cp }: { cp: Checkpoint }) {
  const w = cp.weather;
  return (
    <div className="iw">
      <strong className="iw-title">Checkpoint {cp.sequence}</strong>
      <div className="iw__row">
        <RiskPill level={cp.risk_level} />
        <span className="iw__muted">mile {formatMiles(cp.distance_from_origin_miles)}</span>
      </div>
      <div className="iw__eta">ETA {formatFull(cp.eta)}</div>
      <dl className="iw__grid">
        <dt>Wind</dt>
        <dd>
          {w.wind_mph.toFixed(0)} mph <span className="iw__muted">gusts {w.wind_gust_mph.toFixed(0)}</span>
        </dd>
        <dt>Rain</dt>
        <dd>{w.rain_in_hr.toFixed(2)} in/hr</dd>
        <dt>Snow</dt>
        <dd>{w.snow_in_hr.toFixed(2)} in/hr</dd>
      </dl>
      {cp.risk_reasons.length > 0 && (
        <ul className="iw__reasons">
          {cp.risk_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EndpointMarkers() {
  const analysis = useAppStore((s) => s.analysis);
  if (!analysis) return null;
  return (
    <>
      <Marker longitude={analysis.origin.lng} latitude={analysis.origin.lat} anchor="bottom" offset={[0, -10]} style={{ zIndex: 4 }}>
        <span className="endpoint endpoint--origin" title={`Origin: ${analysis.origin.label}`}>A</span>
      </Marker>
      <Marker longitude={analysis.destination.lng} latitude={analysis.destination.lat} anchor="bottom" offset={[0, -10]} style={{ zIndex: 4 }}>
        <span className="endpoint endpoint--dest" title={`Destination: ${analysis.destination.label}`}>B</span>
      </Marker>
    </>
  );
}

/** The truck's simulated position on the selected route at the slider's time. */
export function TruckMarker() {
  const route = useSelectedRoute();
  const offset = useAppStore((s) => s.forecastHourOffset);
  const baseTime = useAppStore((s) => s.grid?.start_time ?? s.analysis?.request.departure_time);
  const cum = useMemo(() => (route ? cumulativeMiles(route.geometry) : []), [route]);

  if (!route || !baseTime) return null;
  const truck = truckPositionAt(route, cum, Date.parse(baseTime) + offset * 3_600_000);
  if (truck.state === 'waiting') return null; // still at the origin, under the "A" pin
  const label = truck.state === 'arrived' ? 'Arrived' : `Mile ${Math.round(truck.mile)}`;
  return (
    <Marker longitude={truck.position.lng} latitude={truck.position.lat} anchor="bottom" offset={[0, -6]} style={{ zIndex: 5 }}>
      <span className={`truck truck--${truck.state}`} aria-label={`Truck position: ${label}`}>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            fill="currentColor"
            d="M3 6h11v9H3zM14 9h4l3 3.5V15h-7zM6.5 18.5a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Zm11 0a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Z"
          />
        </svg>
        <span className="truck__label">{label}</span>
      </span>
    </Marker>
  );
}
