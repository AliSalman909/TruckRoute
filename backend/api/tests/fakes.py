"""Test doubles: an in-memory routing provider and a weather stub."""

from datetime import datetime, timedelta

from api.services import spatial
from api.services.models import LatLng, Place, RouteCandidate
from api.services.weather import HourlySeries, floor_hour, location_key

ORIGIN = LatLng(41.0, -95.0)
DEST = spatial.project(ORIGIN, 90, 300 * spatial.METERS_PER_MILE)

# What the fake geocoder knows. Results are listed best match first, like the real one.
GAZETTEER: dict[str, list[Place]] = {
    "omaha, ne": [Place("Omaha, NE, USA", ORIGIN, "USA")],
    "denver, co": [Place("Denver, CO, USA", DEST, "USA")],
    "springfield": [
        Place("Springfield, MO, USA", LatLng(37.197, -93.281), "USA"),
        Place("Springfield, IL, USA", LatLng(39.797, -89.646), "USA"),
    ],
    "toronto": [
        Place("Toronto, ON, Canada", LatLng(43.65, -79.38), "CAN"),
        Place("Toronto, OH, USA", LatLng(40.46, -80.60), "USA"),
    ],
    "vancouver, bc": [Place("Vancouver, BC, Canada", LatLng(49.28, -123.12), "CAN")],
}

# Extra known addresses for reverse geocoding (nearest within ~1.5 degrees wins).
REVERSE_EXTRA = [
    Place("Moline, IL, USA", LatLng(41.5, -90.5), "USA"),
    Place("Anchorage, AK, USA", LatLng(61.2, -149.9), "USA"),
    Place("Honolulu, HI, USA", LatLng(21.3, -157.86), "USA"),
    Place("London, UK", LatLng(51.5, -0.12), "GBR"),
    Place("Paris, France", LatLng(48.85, 2.35), "FRA"),
]


def straight_route(points: list[LatLng], mph: float = 60.0, summary: str = "I-80") -> RouteCandidate:
    cum = spatial.cumulative_distances(points)
    dist = cum[-1]
    dur = dist / spatial.METERS_PER_MILE / mph * 3600
    return RouteCandidate(
        encoded_polyline=spatial.encode_polyline(points),
        distance_m=dist,
        duration_s=dur,
        summary=summary,
        time_profile=[(0.0, 0.0), (dist, dur)],
        start=points[0],
        end=points[-1],
    )


class FakeProvider:
    name = "fake"

    def __init__(self, primary_count: int = 1, detour_mph: float = 55.0):
        self.primary_count = primary_count
        self.detour_mph = detour_mph
        self.via_calls: list[LatLng] = []
        self.searches: list[str] = []

    async def search_places(self, query, limit):
        self.searches.append(query)
        return GAZETTEER.get(query.strip().casefold(), [])[:limit]

    async def reverse_geocode(self, point):
        known = [p for results in GAZETTEER.values() for p in results] + REVERSE_EXTRA
        nearest = min(known, key=lambda p: (p.point.lat - point.lat) ** 2 + (p.point.lng - point.lng) ** 2)
        close = abs(nearest.point.lat - point.lat) < 1.5 and abs(nearest.point.lng - point.lng) < 1.5
        return nearest if close else None

    async def compute_routes(self, start, end, departure, via=None):
        if via is None:
            routes = [straight_route([ORIGIN, DEST])]
            if self.primary_count > 1:
                north = spatial.project(spatial.project(ORIGIN, 90, 150 * spatial.METERS_PER_MILE), 0, 60_000)
                routes.append(straight_route([ORIGIN, north, DEST], summary="US-30"))
            return routes[: self.primary_count]
        self.via_calls.append(via)
        route = straight_route([ORIGIN, via, DEST], mph=self.detour_mph, summary="Detour")
        route.via_waypoint = via
        return [route]


def weather_stub(wind_by_hour=None, default_wind=5.0):
    """Returns an async replacement for weather.fetch_hourly with uniform wind per hour offset."""
    wind_by_hour = wind_by_hour or {}

    async def fetch_hourly(client, locations, start, end):
        start = floor_hour(start)
        hours = int((end - start).total_seconds() // 3600) + 2
        winds = tuple(wind_by_hour.get(h, default_wind) for h in range(hours))
        zeros = (0.0,) * hours
        series = HourlySeries(start=start, wind=winds, gust=winds, rain=zeros, snow=zeros)
        return {location_key(p): series for p in locations}

    return fetch_hourly


def future(hours: int = 24) -> datetime:
    from django.utils import timezone

    return floor_hour(timezone.now() + timedelta(hours=hours))
