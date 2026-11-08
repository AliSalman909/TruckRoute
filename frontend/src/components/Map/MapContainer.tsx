import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import Map, {
  NavigationControl,
  ScaleControl,
  useMap,
  type MapLayerMouseEvent,
} from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { boundsOf } from '../../lib/geo';
import { useAppStore } from '../../store/useAppStore';
import { CheckpointMarkers, EndpointMarkers, TruckMarker } from './Markers';
import { MapLegend } from './MapLegend';
import { ROUTE_HIT_LAYER, RouteLayers } from './RoutePolyline';

// deck.gl is the heaviest dependency; load it after the map is interactive.
const HeatmapLayer = lazy(() => import('./HeatmapLayer'));

// OpenFreeMap: free OpenStreetMap vector tiles, no API key (the basemap FreeRoute itself uses).
const MAP_STYLES = {
  light: import.meta.env.VITE_MAP_STYLE_LIGHT || 'https://tiles.openfreemap.org/styles/positron',
  dark: import.meta.env.VITE_MAP_STYLE_DARK || 'https://tiles.openfreemap.org/styles/dark',
};

export function MapContainer() {
  const scheme = useColorScheme();
  const selectRoute = useAppStore((s) => s.selectRoute);
  const [cursor, setCursor] = useState<string | undefined>();

  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const routeId = e.features?.[0]?.properties?.routeId;
      if (typeof routeId === 'string') selectRoute(routeId);
    },
    [selectRoute],
  );

  return (
    <>
      <Map
        id="main"
        initialViewState={{ longitude: -96.5, latitude: 39.5, zoom: 3.4 }}
        mapStyle={MAP_STYLES[scheme]}
        style={{ position: 'absolute', inset: 0 }}
        interactiveLayerIds={[ROUTE_HIT_LAYER]}
        onClick={onClick}
        onMouseEnter={() => setCursor('pointer')}
        onMouseLeave={() => setCursor(undefined)}
        cursor={cursor}
        attributionControl={{ compact: true }}
        dragRotate={false}
        touchPitch={false}
      >
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-left" unit="imperial" />
        <FitToRoutes />
        <RouteLayers />
        <Suspense fallback={null}>
          <HeatmapLayer />
        </Suspense>
        <CheckpointMarkers />
        <EndpointMarkers />
        <TruckMarker />
      </Map>
      <MapLegend />
    </>
  );
}

function FitToRoutes() {
  const { current: map } = useMap();
  const analysis = useAppStore((s) => s.analysis);
  useEffect(() => {
    if (!map || !analysis) return;
    const bounds = boundsOf(analysis.routes);
    if (bounds) {
      map.fitBounds(bounds, { padding: { top: 70, bottom: 200, left: 60, right: 60 }, duration: 900 });
    }
  }, [map, analysis]);
  return null;
}

function useColorScheme(): 'light' | 'dark' {
  const query = '(prefers-color-scheme: dark)';
  const [dark, setDark] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return dark ? 'dark' : 'light';
}
