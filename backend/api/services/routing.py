
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections import defaultdict
from datetime import datetime
from typing import Protocol

import httpx
from django.conf import settings
from django.core.cache import cache

from ..exceptions import RoutingError
from . import spatial
from .models import LatLng, Place, RouteCandidate

log = logging.getLogger(__name__)

TARGET_ROUTE_COUNT = 3
MIN_DETOUR_MILES = 15
MAX_DETOUR_MILES = 120
DETOUR_FRACTION = 0.15  # waypoint offset as a share of route length
MAX_DURATION_RATIO = 1.6  # reject generated alternatives much slower than the fastest
OVERLAP_LIMIT = 0.85  # routes sharing more than this share of their length are "the same"


class RoutingProvider(Protocol):
    name: str

    async def search_places(self, query: str, limit: int) -> list[Place]:
        """Geocoder matches for `query`, best first (no country filtering)."""
        ...

    async def reverse_geocode(self, point: LatLng) -> Place | None:
        """Nearest known address to `point` (with its country), or None."""
        ...

    async def compute_routes(
        self,
        start: LatLng,
        end: LatLng,
        departure: datetime,
        via: LatLng | None = None,
    ) -> list[RouteCandidate]:
        """Routes from start to end. With `via`, a single route through it."""
        ...


# --- FreeRoute ---------------------------------------------------------------------------

class FreeRouteProvider:
    name = "freeroute"

    ALTERNATIVES_MAX_M = 90_000  # stay under openrouteservice's 100 km alternative-routes cap
    ENDPOINT_RADIUS_M = 5_000  # geocoded city centroids may sit off the road graph
    VIA_RADIUS_M = 25_000  # detour waypoints land in arbitrary fields; snap to nearest road
    GEOCODE_CACHE_S = 24 * 3600

    _HIGHWAY_REF_RE = re.compile(r"\b(I|US|SR|[A-Z]{2})[ -]?\d+[A-Z]?\b")

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str, profile: str):
        self.client = client
        self.base_url = base_url
        self.api_key = api_key
        self.profile = profile

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": settings.HTTP_USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # -- geocoding --

    async def search_places(self, query: str, limit: int) -> list[Place]:
        """GET /geocode/search. Cached 24 h: autocomplete repeats the same prefixes a lot."""
        query = query.strip()
        cache_key = "fr:geo:" + hashlib.sha1(f"{query.casefold()}|{limit}".encode()).hexdigest()
        cached = await cache.aget(cache_key)
        if cached is not None:
            return cached

        resp = await self._request("GET", "/geocode/search", params={"q": query, "limit": limit})
        places = self._parse_places(resp, fallback_label=query)
        await cache.aset(cache_key, places, self.GEOCODE_CACHE_S)
        return places

    async def reverse_geocode(self, point: LatLng) -> Place | None:
        """GET /geocode/reverse: the nearest address to a coordinate (None over open water)."""
        cache_key = f"fr:rev:{point.lat:.3f}:{point.lng:.3f}"
        cached = await cache.aget(cache_key)
        if cached is not None:
            return cached or None  # "" is cached for "nothing here"
        resp = await self._request(
            "GET", "/geocode/reverse", params={"lat": point.lat, "lon": point.lng, "limit": 1}
        )
        places = self._parse_places(resp, fallback_label=f"{point.lat:.4f}, {point.lng:.4f}")
        await cache.aset(cache_key, places[0] if places else "", self.GEOCODE_CACHE_S)
        return places[0] if places else None

    @staticmethod
    def _parse_places(resp: httpx.Response, fallback_label: str) -> list[Place]:
        if resp.status_code >= 500:
            raise RoutingError("FreeRoute geocoding is unavailable. Try again shortly.", status=503)
        places = []
        for feature in resp.json().get("features") or []:
            lng, lat = feature["geometry"]["coordinates"][:2]
            props = feature.get("properties", {})
            places.append(
                Place(
                    label=props.get("label") or props.get("name") or fallback_label,
                    point=LatLng(float(lat), float(lng)),
                    country_code=(props.get("countrycode") or "").upper(),
                )
            )
        return places

    # -- directions --

    async def compute_routes(self, start, end, departure, via=None):
        stops = [start] + ([via] if via else []) + [end]
        body: dict = {
            "coordinates": [[p.lng, p.lat] for p in stops],
            "instructions": True,
            "radiuses": [self.ENDPOINT_RADIUS_M]
            + ([self.VIA_RADIUS_M] if via else [])
            + [self.ENDPOINT_RADIUS_M],
        }
        want_alternatives = via is None and spatial.distance_m(start, end) <= self.ALTERNATIVES_MAX_M
        if want_alternatives:
            body["alternative_routes"] = {"target_count": 3, "weight_factor": 1.6, "share_factor": 0.6}

        data = await self._directions(body)
        if data is None and want_alternatives:
            body.pop("alternative_routes")
            data = await self._directions(body)
        if data is None:
            if via is not None:
                return []  # unroutable detour waypoint: caller just skips it
            raise RoutingError("No drivable route found between these locations.", status=422)

        return [self._parse(f, start, end, via) for f in data.get("features", [])]

    async def _directions(self, body: dict) -> dict | None:
        """Parsed GeoJSON, or None when FreeRoute fails to route (it answers HTTP 500)."""
        resp = await self._request("POST", f"/directions/{self.profile}", json=body)
        if resp.status_code >= 500:
            log.info("FreeRoute directions returned %s for %d coordinates", resp.status_code, len(body["coordinates"]))
            return None
        return resp.json()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = await self.client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise RoutingError("Could not reach FreeRoute.", status=502) from exc
        if resp.status_code in (401, 403):
            raise RoutingError("FreeRoute rejected the API key (check FREEROUTE_API_KEY).", status=502)
        if resp.status_code == 429:
            raise RoutingError("FreeRoute rate limit reached (60 requests/min). Try again in a minute.", status=503)
        if 400 <= resp.status_code < 500:
            raise RoutingError(f"FreeRoute: {_error_message(resp)}", status=422)
        return resp

    @classmethod
    def _parse(cls, feature: dict, start: LatLng, end: LatLng, via: LatLng | None) -> RouteCandidate:
        points = [LatLng(c[1], c[0]) for c in feature["geometry"]["coordinates"]]
        props = feature.get("properties", {})
        profile: list[tuple[float, float]] = []
        road_m: dict[str, float] = defaultdict(float)
        d = t = 0.0
        for segment in props.get("segments", []):
            for step in segment.get("steps", []):
                d += float(step.get("distance", 0))
                t += float(step.get("duration", 0))
                profile.append((d, t))
                label = cls._road_label(step.get("name", ""))
                if label:
                    road_m[label] += float(step.get("distance", 0))
        summary = props.get("summary", {})
        distance = float(summary.get("distance", d))
        duration = float(summary.get("duration", t))
        top_roads = [name for name, _ in sorted(road_m.items(), key=lambda kv: -kv[1])[:2]]
        return RouteCandidate(
            encoded_polyline=spatial.encode_polyline(points),
            distance_m=distance,
            duration_s=duration,
            summary=" · ".join(top_roads) or "Route",
            time_profile=spatial.normalize_profile(profile, distance, duration),
            start=points[0] if points else start,
            end=points[-1] if points else end,
            via_waypoint=via,
        )

    @classmethod
    def _road_label(cls, name: str) -> str:
        """'Ronald Reagan Memorial Tollway, I 88, IL 110' -> 'I 88'; plain names pass through."""
        name = (name or "").strip()
        if not name or name == "-":
            return ""
        ref = cls._HIGHWAY_REF_RE.search(name)
        return ref.group(0).replace("-", " ") if ref else name.split(",")[0].strip()


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return body.get("message") or body.get("error") or f"HTTP {resp.status_code}"
    except ValueError:
        return f"HTTP {resp.status_code}"


def get_provider(client: httpx.AsyncClient) -> RoutingProvider:
    return FreeRouteProvider(
        client,
        base_url=settings.FREEROUTE_BASE_URL,
        api_key=settings.FREEROUTE_API_KEY,
        profile=settings.FREEROUTE_PROFILE,
    )


# --- 3-route guarantee -------------------------------------------------------------------

def _footprint(route: RouteCandidate) -> tuple[list[LatLng], set[tuple[int, int]]]:
    """Points every ~2 km along the route and the ~2 km grid cells they fall in."""
    pts = spatial.decode_polyline(route.encoded_polyline)
    samples = spatial.resample(pts, spatial.cumulative_distances(pts), 2000)
    cells = {(math.floor(p.lat / 0.02), math.floor(p.lng / 0.02)) for p in samples}
    return samples, cells


def overlap_ratio(candidate: RouteCandidate, existing: RouteCandidate) -> float:
    """Share of `candidate` (by sampled length) lying within ~2 km of `existing`."""
    samples, _ = _footprint(candidate)
    _, cells = _footprint(existing)
    if not samples:
        return 1.0
    hits = 0
    for p in samples:
        ci, cj = math.floor(p.lat / 0.02), math.floor(p.lng / 0.02)
        if any((ci + di, cj + dj) in cells for di in (-1, 0, 1) for dj in (-1, 0, 1)):
            hits += 1
    return hits / len(samples)


def is_distinct(candidate: RouteCandidate, existing: list[RouteCandidate]) -> bool:
    return all(overlap_ratio(candidate, r) < OVERLAP_LIMIT for r in existing)


def detour_waypoints(base: RouteCandidate) -> list[LatLng]:
    """Waypoints perpendicular to the origin->destination bearing, from the route midpoint.

    Offset scales with trip length (15% of it, clamped to 15-120 miles): a fixed
    15-mile nudge on a 1,000-mile trip usually snaps back onto the same interstate.
    """
    pts = spatial.decode_polyline(base.encoded_polyline)
    cum = spatial.cumulative_distances(pts)
    total = cum[-1]
    mid, _ = spatial.point_at_distance(pts, cum, total / 2)
    bearing = spatial.bearing_deg(pts[0], pts[-1])
    offset = min(max(total * DETOUR_FRACTION, MIN_DETOUR_MILES * spatial.METERS_PER_MILE),
                 MAX_DETOUR_MILES * spatial.METERS_PER_MILE)
    waypoints = []
    for scale in (1.0, 2.0):
        for sign in (1, -1):
            waypoints.append(spatial.project(mid, bearing + sign * 90, offset * scale))
    return waypoints


async def get_route_options(
    provider: RoutingProvider, start: LatLng, end: LatLng, departure: datetime
) -> tuple[list[RouteCandidate], list[str]]:
    """Up to three distinct routes, generating detours when the provider returns fewer."""
    warnings: list[str] = []
    primary = await provider.compute_routes(start, end, departure)
    if not primary:
        raise RoutingError("No drivable route found between these locations.", status=422)

    routes: list[RouteCandidate] = []
    for candidate in primary:
        if not routes or is_distinct(candidate, routes):
            routes.append(candidate)
    if len(routes) >= TARGET_ROUTE_COUNT:
        return routes[:TARGET_ROUTE_COUNT], warnings

    fastest = min(r.duration_s for r in routes)
    waypoints = detour_waypoints(routes[0])
    results = await asyncio.gather(
        *(provider.compute_routes(start, end, departure, via=wp) for wp in waypoints),
        return_exceptions=True,
    )
    candidates = []
    for result in results:
        if isinstance(result, BaseException):
            log.info("Detour route request failed: %s", result)
        elif result and result[0].duration_s <= fastest * MAX_DURATION_RATIO:
            candidates.append(result[0])
    # Fastest first: a detour that snaps onto a highway beats one that wanders on minor roads.
    for candidate in sorted(candidates, key=lambda r: r.duration_s):
        if len(routes) >= TARGET_ROUTE_COUNT:
            break
        if is_distinct(candidate, routes):
            routes.append(candidate)

    if len(routes) < TARGET_ROUTE_COUNT:
        warnings.append(
            f"Only {len(routes)} distinct reasonable route(s) exist for this trip; "
            "generated detours were too slow or overlapped existing routes."
        )
    return routes, warnings
