import { useMemo } from 'react';
import { Layer, Source } from 'react-map-gl/maplibre';
import type { Feature, FeatureCollection, LineString } from 'geojson';
import { RISK_COLOR } from '../../lib/risk';
import { useAppStore } from '../../store/useAppStore';
import type { RouteResult } from '../../types';

/** Invisible wide line under every route: makes routes easy to click. */
export const ROUTE_HIT_LAYER = 'routes-hit';
const ROUTES_BASE_LAYER = 'routes-other';

type SegmentProps = { routeId: string; color: string; selected: boolean };

const toCoords = (route: RouteResult, from = 0, to = route.geometry.length - 1) =>
  route.geometry.slice(from, to + 1).map((p) => [p.lng, p.lat]);

/**
 * Routes drawn as risk-coloured segments: one GeoJSON line per checkpoint,
 * covering that checkpoint's slice of the geometry (`path_range` from the API,
 * midpoint to midpoint), so colours match the miles each checkpoint represents.
 * The selected route sits on top with a casing; the others are thinner and faded.
 */
export function RouteLayers() {
  const routes = useAppStore((s) => s.analysis?.routes);
  const selectedId = useAppStore((s) => s.selectedRouteId);

  const segments = useMemo<FeatureCollection<LineString, SegmentProps>>(() => {
    const features: Feature<LineString, SegmentProps>[] = [];
    for (const route of routes ?? []) {
      for (const cp of route.checkpoints) {
        const coords = toCoords(route, cp.path_range[0], cp.path_range[1]);
        if (coords.length < 2) continue;
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: coords },
          properties: { routeId: route.id, color: RISK_COLOR[cp.risk_level], selected: route.id === selectedId },
        });
      }
    }
    return { type: 'FeatureCollection', features };
  }, [routes, selectedId]);

  const outlines = useMemo<FeatureCollection<LineString, { routeId: string; selected: boolean }>>(
    () => ({
      type: 'FeatureCollection',
      features: (routes ?? []).map((route) => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: toCoords(route) },
        properties: { routeId: route.id, selected: route.id === selectedId },
      })),
    }),
    [routes, selectedId],
  );

  if (!routes) return null;
  return (
    <>
      <Source id="route-outlines" type="geojson" data={outlines}>
        <Layer
          id={ROUTE_HIT_LAYER}
          type="line"
          paint={{ 'line-color': '#000', 'line-opacity': 0, 'line-width': 16 }}
        />
        <Layer
          id="route-casing"
          type="line"
          filter={['==', ['get', 'selected'], true]}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': '#ffffff', 'line-width': 11, 'line-opacity': 0.95 }}
        />
      </Source>
      <Source id="route-segments" type="geojson" data={segments}>
        <Layer
          id={ROUTES_BASE_LAYER}
          type="line"
          beforeId="route-casing"
          filter={['==', ['get', 'selected'], false]}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': ['get', 'color'], 'line-width': 3.5, 'line-opacity': 0.55 }}
        />
        <Layer
          id="routes-selected"
          type="line"
          filter={['==', ['get', 'selected'], true]}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': ['get', 'color'], 'line-width': 6 }}
        />
      </Source>
    </>
  );
}
