import type { LatLng, RouteResult } from '../types';

const R_MILES = 3958.8;
const toRad = (d: number) => (d * Math.PI) / 180;

export function haversineMiles(a: LatLng, b: LatLng): number {
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R_MILES * Math.asin(Math.sqrt(h));
}

export function cumulativeMiles(points: LatLng[]): number[] {
  const out = [0];
  for (let i = 1; i < points.length; i++) out.push(out[i - 1] + haversineMiles(points[i - 1], points[i]));
  return out;
}

export interface TruckPosition {
  position: LatLng;
  state: 'waiting' | 'driving' | 'arrived';
  mile: number;
}

/**
 * Where the truck is at `when` on `route`: time -> route mile from checkpoint
 * ETAs, then route mile -> coordinate along the geometry.
 */
export function truckPositionAt(route: RouteResult, cum: number[], when: number): TruckPosition {
  const cps = route.checkpoints;
  const first = cps[0];
  const last = cps[cps.length - 1];
  if (when <= Date.parse(first.eta)) return { position: route.geometry[0], state: 'waiting', mile: 0 };
  if (when >= Date.parse(last.eta)) {
    return { position: route.geometry[route.geometry.length - 1], state: 'arrived', mile: last.distance_from_origin_miles };
  }
  let i = 0;
  while (i < cps.length - 2 && Date.parse(cps[i + 1].eta) < when) i++;
  const t0 = Date.parse(cps[i].eta);
  const t1 = Date.parse(cps[i + 1].eta);
  const f = t1 > t0 ? (when - t0) / (t1 - t0) : 0;
  const mile = cps[i].distance_from_origin_miles + f * (cps[i + 1].distance_from_origin_miles - cps[i].distance_from_origin_miles);

  // Geometry miles differ slightly from the provider's route miles; scale between them.
  const geoTotal = cum[cum.length - 1] || 1;
  const target = (mile / (last.distance_from_origin_miles || 1)) * geoTotal;
  let j = 0;
  while (j < cum.length - 2 && cum[j + 1] < target) j++;
  const seg = cum[j + 1] - cum[j];
  const g = seg > 0 ? (target - cum[j]) / seg : 0;
  const a = route.geometry[j];
  const b = route.geometry[Math.min(j + 1, route.geometry.length - 1)];
  return { position: { lat: a.lat + (b.lat - a.lat) * g, lng: a.lng + (b.lng - a.lng) * g }, state: 'driving', mile };
}

/** [[west, south], [east, north]] covering every route, for map.fitBounds. */
export function boundsOf(routes: RouteResult[]): [[number, number], [number, number]] | null {
  let north = -90, south = 90, east = -180, west = 180;
  let any = false;
  for (const r of routes) {
    for (const p of r.geometry) {
      any = true;
      if (p.lat > north) north = p.lat;
      if (p.lat < south) south = p.lat;
      if (p.lng > east) east = p.lng;
      if (p.lng < west) west = p.lng;
    }
  }
  return any ? [[west, south], [east, north]] : null;
}
