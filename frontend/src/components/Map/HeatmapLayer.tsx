import { useEffect, useMemo, useState } from 'react';
import { useControl, useMap } from 'react-map-gl/maplibre';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { HeatmapLayer as DeckHeatmapLayer } from '@deck.gl/aggregation-layers';
import { METRICS } from '../../lib/risk';
import { useAppStore } from '../../store/useAppStore';

interface HeatPoint {
  position: [number, number];
  weight: number;
}

/**
 * Corridor weather heatmap: deck.gl HeatmapLayer over the MapLibre map.
 *
 * `aggregation: 'MEAN'` colours each pixel by the *average* value nearby
 * (e.g. 38 mph wind), not by point density, which is what a weather map needs.
 * Moving the slider only re-slices data already in memory (useMemo); no new API calls.
 *
 * The overlay is NOT interleaved: in deck.gl 9.1, HeatmapLayer interleaved into
 * MapLibre renders only isolated points instead of a continuous field (verified in
 * a real browser). It therefore draws above the route lines, so opacity stays moderate.
 */
export default function HeatmapLayer() {
  const grid = useAppStore((s) => s.grid);
  const offset = useAppStore((s) => s.forecastHourOffset);
  const metric = useAppStore((s) => s.heatmapMetric);
  const visible = useAppStore((s) => s.heatmapVisible);
  const zoom = useZoom();

  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay({ interleaved: false, layers: [] }));

  const data = useMemo<HeatPoint[]>(() => {
    if (!grid) return [];
    const { toWeight } = METRICS[metric];
    return grid.points.map((p) => {
      const series = p[metric];
      return { position: [p.lng, p.lat], weight: toWeight(series[Math.min(offset, series.length - 1)] ?? 0) };
    });
  }, [grid, metric, offset]);

  // Size the kernel so neighbouring grid cells blend at any zoom (MapLibre uses 512 px tiles).
  const radiusPixels = useMemo(() => {
    if (!grid || !grid.points.length) return 30;
    const lat = grid.points.reduce((sum, p) => sum + p.lat, 0) / grid.points.length;
    const metersPerPixel = (78271.517 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
    const spacingMeters = grid.spacing_deg * 111_320;
    return Math.min(220, Math.max(16, (spacingMeters * 2.2) / metersPerPixel));
  }, [grid, zoom]);

  useEffect(() => {
    const spec = METRICS[metric];
    overlay.setProps({
      layers:
        visible && data.length
          ? [
              new DeckHeatmapLayer<HeatPoint>({
                id: 'corridor-weather',
                data,
                getPosition: (d) => d.position,
                getWeight: (d) => d.weight,
                aggregation: 'MEAN',
                colorDomain: spec.domain,
                colorRange: spec.colors,
                radiusPixels,
                intensity: 1,
                threshold: 0.05,
                opacity: 0.6,
                debounceTimeout: 50,
                updateTriggers: { getWeight: [metric, offset] },
              }),
            ]
          : [],
    });
  }, [overlay, data, radiusPixels, metric, offset, visible]);

  return null;
}

function useZoom(): number {
  const { current: map } = useMap();
  const [zoom, setZoom] = useState(() => map?.getZoom() ?? 4);
  useEffect(() => {
    if (!map) return;
    const update = () => setZoom(map.getZoom());
    update();
    map.on('zoomend', update);
    return () => {
      map.off('zoomend', update);
    };
  }, [map]);
  return zoom;
}
