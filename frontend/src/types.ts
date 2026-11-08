/** Types mirroring the Django API contract (see backend/api/services/analysis.py). */

export type RiskLevel = 'Low' | 'Moderate' | 'High' | 'Severe' | 'No Travel';
export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';
export type IntervalMiles = 10 | 25 | 50;

export interface LatLng {
  lat: number;
  lng: number;
}

export interface AnalyzeRequest {
  origin: string;
  destination: string;
  departure_time: string;
  load_weight: number;
  interval_miles: IntervalMiles;
  /** Set when the user picked a suggestion: the backend uses exactly this point. */
  origin_location?: LatLng | null;
  destination_location?: LatLng | null;
}

/** One entry in the origin/destination dropdown (GET /places/). */
export interface PlaceSuggestion extends LatLng {
  label: string;
}

export interface PlacesResponse {
  status: 'SUCCESS';
  query: string;
  allowed_area: string;
  results: PlaceSuggestion[];
}

/** How the backend understood a typed or picked place. */
export interface ResolvedPlace extends LatLng {
  label: string;
  query: string;
  matched_by: 'suggestion' | 'search' | 'coordinates';
}

export interface CheckpointWeather {
  wind_mph: number;
  wind_gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  forecast_hour: string;
}

export interface Checkpoint {
  sequence: number;
  lat: number;
  lng: number;
  eta: string;
  distance_from_origin_miles: number;
  segment_miles: number;
  path_range: [number, number];
  weather: CheckpointWeather;
  risk_level: RiskLevel;
  risk_reasons: string[];
}

export type RiskCounts = Record<RiskKey, number>;

export interface RouteResult {
  id: string;
  rank: number;
  is_recommended: boolean;
  is_viable: boolean;
  summary: string;
  is_generated_detour: boolean;
  total_distance_miles: number;
  total_duration_mins: number;
  departure_time: string;
  arrival_time: string;
  risk_summary: RiskCounts;
  risk_miles: RiskCounts;
  avg_risk_score: number;
  max_risk_level: RiskLevel;
  encoded_polyline: string;
  geometry: LatLng[];
  checkpoints: Checkpoint[];
}

export interface SafeDeparture {
  departure_time: string;
  delay_hours: number;
  route_id: string;
  risk_summary: RiskCounts;
  risk_miles: RiskCounts;
}

export interface AnalyzeResponse {
  status: 'SUCCESS';
  all_routes_unsafe: boolean;
  suggested_departure_time: string | null;
  safe_departure: SafeDeparture | null;
  recommended_route_id: string;
  recommendation_reason: string;
  routing_provider: string;
  request: AnalyzeRequest;
  origin: ResolvedPlace;
  destination: ResolvedPlace;
  allowed_area: string;
  forecast_horizon: string;
  warnings: string[];
  routes: RouteResult[];
}

export interface GridPoint {
  lat: number;
  lng: number;
  wind: number[];
  rain: number[];
  snow: number[];
  risk: number[];
}

export interface WeatherGridResponse {
  status: 'SUCCESS';
  start_time: string;
  times: string[];
  spacing_deg: number;
  points: GridPoint[];
}

export interface ApiErrorBody {
  status: 'ERROR';
  error: { code: string; message: string; details: Record<string, unknown> };
}

export type HeatmapMetric = 'risk' | 'wind' | 'rain' | 'snow';
