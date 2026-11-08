import type { HeatmapMetric, RiskKey, RiskLevel } from '../types';

export const RISK_LEVELS: RiskLevel[] = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'];

export const RISK_KEY: Record<RiskLevel, RiskKey> = {
  Low: 'low',
  Moderate: 'moderate',
  High: 'high',
  Severe: 'severe',
  'No Travel': 'no_travel',
};

/** Hex colours; mirrored as CSS custom properties in styles.css. */
export const RISK_COLOR: Record<RiskLevel, string> = {
  Low: '#16a34a',
  Moderate: '#ca8a04',
  High: '#ea580c',
  Severe: '#dc2626',
  'No Travel': '#7e22ce',
};

export const riskColorByKey = (key: RiskKey): string =>
  RISK_COLOR[RISK_LEVELS.find((l) => RISK_KEY[l] === key) ?? 'Low'];

type RGBA = [number, number, number, number];

/**
 * deck.gl HeatmapLayer colour maths (9.1 shader): colour = colorRange at
 * `weight / domain[1]` (measured from 0), alpha fades in as `weight / domain[0]`,
 * and weight <= 0 is discarded. So `toWeight` shifts values that should still
 * paint at zero (Low risk, calm wind) above 0, and `domain[0]` is the fade-in level.
 */
export interface MetricSpec {
  label: string;
  toWeight: (v: number) => number;
  domain: [number, number]; // [fade-in weight, weight at the top colour]
  legend: [number, number]; // natural units shown under the scale bar
  colors: RGBA[];
  format: (v: number) => string;
}

export const METRICS: Record<HeatmapMetric, MetricSpec> = {
  risk: {
    label: 'Risk',
    // level + 1: Low=1 ... No Travel=5, landing on colours 1..5 of the range.
    toWeight: (level) => level + 1,
    domain: [1, 5],
    legend: [0, 4],
    colors: [
      [22, 163, 74, 60],
      [22, 163, 74, 85],
      [234, 179, 8, 165],
      [234, 88, 12, 195],
      [220, 38, 38, 215],
      [126, 34, 206, 235],
    ],
    format: (v) => RISK_LEVELS[Math.min(4, Math.max(0, Math.round(v)))],
  },
  wind: {
    label: 'Wind',
    toWeight: (mph) => mph + 1,
    domain: [1, 56],
    legend: [0, 55],
    colors: [
      [56, 189, 248, 70],
      [56, 189, 248, 130],
      [234, 179, 8, 150],
      [234, 88, 12, 185],
      [220, 38, 38, 210],
      [126, 34, 206, 230],
    ],
    format: (v) => `${Math.round(v)} mph`,
  },
  rain: {
    label: 'Rain',
    toWeight: (v) => v, // dry (0) stays transparent
    domain: [0.02, 0.75],
    legend: [0, 0.75],
    colors: [
      [59, 130, 246, 0],
      [96, 165, 250, 110],
      [37, 99, 235, 160],
      [79, 70, 229, 190],
      [192, 38, 211, 210],
      [220, 38, 38, 230],
    ],
    format: (v) => `${v.toFixed(2)} in/hr`,
  },
  snow: {
    label: 'Snow',
    toWeight: (v) => v,
    domain: [0.05, 2.5],
    legend: [0, 2.5],
    colors: [
      [186, 230, 253, 0],
      [186, 230, 253, 120],
      [125, 211, 252, 170],
      [99, 102, 241, 195],
      [168, 85, 247, 215],
      [126, 34, 206, 235],
    ],
    format: (v) => `${v.toFixed(1)} in/hr`,
  },
};

export const metricGradientCss = (metric: HeatmapMetric): string => {
  const stops = METRICS[metric].colors.map(
    ([r, g, b, a], i, arr) => `rgba(${r},${g},${b},${Math.max(a, 60) / 255}) ${(i / (arr.length - 1)) * 100}%`,
  );
  return `linear-gradient(90deg, ${stops.join(', ')})`;
};
