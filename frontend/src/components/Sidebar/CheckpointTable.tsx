import { useEffect, useRef } from 'react';
import { formatDayTime } from '../../lib/format';
import { useAppStore } from '../../store/useAppStore';
import type { RouteResult } from '../../types';
import { RiskPill } from '../RiskPill';

export function CheckpointTable({ route }: { route: RouteResult }) {
  const active = useAppStore((s) => s.activeCheckpoint);
  const hovered = useAppStore((s) => s.hoveredCheckpoint);
  const setActive = useAppStore((s) => s.setActiveCheckpoint);
  const setHovered = useAppStore((s) => s.setHoveredCheckpoint);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  // Keep the row for a checkpoint clicked on the map in view.
  useEffect(() => {
    if (active?.routeId !== route.id) return;
    bodyRef.current
      ?.querySelector<HTMLTableRowElement>(`[data-seq="${active.sequence}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [active, route.id]);

  return (
    <div className="cp-table-wrap">
      <table className="cp-table">
        <caption className="visually-hidden">Checkpoints for {route.summary}</caption>
        <thead>
          <tr>
            <th scope="col">Mile</th>
            <th scope="col">ETA</th>
            <th scope="col" className="num">Wind</th>
            <th scope="col" className="num">Rain</th>
            <th scope="col" className="num">Snow</th>
            <th scope="col">Risk</th>
          </tr>
        </thead>
        <tbody ref={bodyRef}>
          {route.checkpoints.map((cp) => {
            const isActive = active?.routeId === route.id && active.sequence === cp.sequence;
            const isHovered = hovered?.routeId === route.id && hovered.sequence === cp.sequence;
            const ref = { routeId: route.id, sequence: cp.sequence };
            return (
              <tr
                key={cp.sequence}
                data-seq={cp.sequence}
                className={`${isActive ? 'is-active' : ''}${isHovered ? ' is-hovered' : ''}`}
                onClick={() => setActive(ref)}
                onMouseEnter={() => setHovered(ref)}
                onMouseLeave={() => setHovered(null)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActive(ref);
                  }
                }}
                title={cp.risk_reasons.join('\n') || undefined}
              >
                <td className="mono">{Math.round(cp.distance_from_origin_miles)}</td>
                <td>{formatDayTime(cp.eta)}</td>
                <td className="num mono">{cp.weather.wind_mph.toFixed(0)}</td>
                <td className="num mono">{cp.weather.rain_in_hr.toFixed(2)}</td>
                <td className="num mono">{cp.weather.snow_in_hr.toFixed(1)}</td>
                <td>
                  <RiskPill level={cp.risk_level} compact />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="cp-table__units">Wind mph · rain & snow in/hr · times in your local time zone</p>
    </div>
  );
}
