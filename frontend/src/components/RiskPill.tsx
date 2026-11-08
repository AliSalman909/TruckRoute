import { RISK_KEY } from '../lib/risk';
import type { RiskLevel } from '../types';

export function RiskPill({ level, compact = false }: { level: RiskLevel; compact?: boolean }) {
  return (
    <span className={`risk-pill risk-${RISK_KEY[level]}${compact ? ' risk-pill--compact' : ''}`}>
      <span className="risk-pill__dot" aria-hidden="true" />
      {level}
    </span>
  );
}
