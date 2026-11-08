"""Plain data objects shared by the service modules (no Django dependencies)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LatLng:
    lat: float
    lng: float

    def to_dict(self) -> dict:
        return {"lat": round(self.lat, 5), "lng": round(self.lng, 5)}


@dataclass(frozen=True)
class Place:
    """A resolved location: what the user typed or picked, turned into coordinates."""

    label: str  # human-readable name, e.g. "Springfield, IL, USA"
    point: LatLng
    country_code: str = ""  # ISO-3 code from the geocoder, e.g. "USA"
    source: str = "search"  # "suggestion" (picked from dropdown), "search" (best guess), "coordinates"

    def to_dict(self) -> dict:
        return {"label": self.label, **self.point.to_dict(), "matched_by": self.source}


@dataclass
class RouteCandidate:
    """A route as returned by a routing provider, normalised to one shape."""

    encoded_polyline: str
    distance_m: float
    duration_s: float
    summary: str
    # Monotonic (cumulative metres, cumulative seconds) pairs along the route, built
    # from per-step durations. Lets ETAs reflect slow city miles vs. fast interstate.
    time_profile: list[tuple[float, float]] = field(default_factory=list)
    start: LatLng | None = None
    end: LatLng | None = None
    via_waypoint: LatLng | None = None


@dataclass(frozen=True)
class WeatherSample:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    time: datetime

    def to_dict(self) -> dict:
        return {
            "wind_mph": round(self.wind_mph, 1),
            "wind_gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 2),
            "snow_in_hr": round(self.snow_in_hr, 2),
            "forecast_hour": self.time.isoformat().replace("+00:00", "Z"),
        }


@dataclass
class Checkpoint:
    """A sampled point on a route. Weather and risk are attached after scoring."""

    sequence: int
    position: LatLng
    distance_m: float  # along the route, from the origin
    offset_s: float  # travel time from departure to this point
    segment_m: float  # route miles this checkpoint represents (for "miles at risk")
    path_start_index: int  # slice of the route geometry this checkpoint colours
    path_end_index: int


@dataclass
class RoutePlan:
    """A route plus its checkpoints; independent of departure time."""

    id: str
    route: RouteCandidate
    geometry: list[LatLng]
    checkpoints: list[Checkpoint]
