import { useState } from 'react';
import { RISK_COLOR, RISK_LEVELS } from '../../lib/risk';
import { useAppStore } from '../../store/useAppStore';

export function MapLegend() {
  const hasAnalysis = useAppStore((s) => !!s.analysis);
  const [open, setOpen] = useState(true);
  if (!hasAnalysis) return null;
  return (
    <div className={`map-legend${open ? '' : ' is-collapsed'}`}>
      <button type="button" className="map-legend__toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Legend
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" />
        </svg>
      </button>
      {open && (
        <ul className="map-legend__list">
          {RISK_LEVELS.map((l) => (
            <li key={l}>
              <span className="swatch-line" style={{ background: RISK_COLOR[l] }} />
              {l}
            </li>
          ))}
          <li className="map-legend__sep">
            <span className="swatch-line swatch-line--selected" />
            Selected route
          </li>
          <li>
            <span className="swatch-line swatch-line--other" />
            Other routes
          </li>
        </ul>
      )}
    </div>
  );
}
