"""Polyline decoding, geodesic distance and checkpoint generation.

Distances use the WGS84 ellipsoid (pyproj.Geod), which is more accurate than
the spherical Haversine formula (~0.5% error) and costs nothing extra.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right

from pyproj import Geod

from .models import Checkpoint, LatLng, RouteCandidate

GEOD = Geod(ellps="WGS84")
METERS_PER_MILE = 1609.344


# --- Polylines -------------------------------------------------------------------

def decode_polyline(encoded: str, precision: int = 5) -> list[LatLng]:
    """Decode an encoded polyline (the standard "Google polyline" algorithm, precision 5)."""
    factor = 10**precision
    points: list[LatLng] = []
    index = lat = lng = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        points.append(LatLng(lat / factor, lng / factor))
    return points


def encode_polyline(points: list[LatLng], precision: int = 5) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lng = 0
    for p in points:
        lat, lng = round(p.lat * factor), round(p.lng * factor)
        for delta in (lat - prev_lat, lng - prev_lng):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lng = lat, lng
    return "".join(out)


def simplify(points: list[LatLng], tolerance_m: float = 15.0) -> list[LatLng]:
    """Ramer-Douglas-Peucker on a local equirectangular projection (iterative)."""
    n = len(points)
    if n < 3:
        return list(points)
    cos_lat = math.cos(math.radians(sum(p.lat for p in points) / n))
    xy = [(p.lng * 111_320 * cos_lat, p.lat * 111_320) for p in points]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_m * tolerance_m
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = xy[first], xy[last]
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        worst, worst_d2 = -1, tol2
        for i in range(first + 1, last):
            px, py = xy[i]
            if seg2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg2))
                d2 = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d2 > worst_d2:
                worst, worst_d2 = i, d2
        if worst != -1:
            keep[worst] = True
            stack.append((first, worst))
            stack.append((worst, last))
    return [p for p, k in zip(points, keep) if k]


# --- Geodesy -----------------------------------------------------------------------

def distance_m(a: LatLng, b: LatLng) -> float:
    return GEOD.inv(a.lng, a.lat, b.lng, b.lat)[2]


def bearing_deg(a: LatLng, b: LatLng) -> float:
    return GEOD.inv(a.lng, a.lat, b.lng, b.lat)[0]


def project(origin: LatLng, azimuth_deg: float, dist_m: float) -> LatLng:
    lng, lat, _ = GEOD.fwd(origin.lng, origin.lat, azimuth_deg, dist_m)
    return LatLng(lat, lng)


def cumulative_distances(points: list[LatLng]) -> list[float]:
    """Cumulative geodesic distance (metres) at each vertex."""
    if len(points) < 2:
        return [0.0] * len(points)
    _, _, legs = GEOD.inv(
        [p.lng for p in points[:-1]],
        [p.lat for p in points[:-1]],
        [p.lng for p in points[1:]],
        [p.lat for p in points[1:]],
    )
    cum = [0.0]
    for leg in legs:
        cum.append(cum[-1] + leg)
    return cum


def point_at_distance(points: list[LatLng], cum: list[float], target_m: float) -> tuple[LatLng, int]:
    """Coordinate `target_m` metres along the polyline, plus the vertex index before it."""
    if target_m <= 0 or len(points) == 1:
        return points[0], 0
    if target_m >= cum[-1]:
        return points[-1], len(points) - 1
    i = min(bisect_right(cum, target_m) - 1, len(points) - 2)
    seg = cum[i + 1] - cum[i]
    if seg <= 0:
        return points[i], i
    a, b = points[i], points[i + 1]
    return project(a, bearing_deg(a, b), target_m - cum[i]), i


def nearest_vertex_index(cum: list[float], target_m: float) -> int:
    i = bisect_left(cum, target_m)
    if i <= 0:
        return 0
    if i >= len(cum):
        return len(cum) - 1
    return i if cum[i] - target_m < target_m - cum[i - 1] else i - 1


def resample(points: list[LatLng], cum: list[float], step_m: float) -> list[LatLng]:
    """Evenly spaced points along a polyline (always includes both ends)."""
    if not points:
        return []
    total = cum[-1]
    out = [point_at_distance(points, cum, d)[0] for d in _frange(0.0, total, step_m)]
    out.append(points[-1])
    return out


def _frange(start: float, stop: float, step: float):
    k = 0
    while start + k * step < stop:
        yield start + k * step
        k += 1


# --- Time along route ---------------------------------------------------------------

def normalize_profile(
    profile: list[tuple[float, float]], distance_m: float, duration_s: float
) -> list[tuple[float, float]]:
    """Scale a step-based profile so its end matches the route's distance and duration."""
    cleaned = [(0.0, 0.0)]
    for d, t in profile:
        if d > cleaned[-1][0] and t >= cleaned[-1][1]:
            cleaned.append((d, t))
    last_d, last_t = cleaned[-1]
    if last_d <= 0 or last_t <= 0:
        return [(0.0, 0.0), (distance_m, duration_s)]
    sd, st = distance_m / last_d, duration_s / last_t
    return [(d * sd, t * st) for d, t in cleaned]


def time_at_distance(profile: list[tuple[float, float]], d: float) -> float:
    """Linear interpolation of elapsed seconds at route distance `d`."""
    if d <= profile[0][0]:
        return profile[0][1]
    if d >= profile[-1][0]:
        return profile[-1][1]
    dists = [p[0] for p in profile]
    i = bisect_right(dists, d) - 1
    (d0, t0), (d1, t1) = profile[i], profile[i + 1]
    return t0 + (t1 - t0) * (d - d0) / (d1 - d0)


# --- Checkpoints -------------------------------------------------------------------

def build_checkpoints(
    route: RouteCandidate, points: list[LatLng], interval_miles: int
) -> list[Checkpoint]:
    """Sample the route at the origin, every `interval_miles`, and the destination.

    Each checkpoint represents the route miles halfway to its neighbours, so the
    `segment_m` values add up to the full route length. That is what lets the
    ranking compare "Severe miles" rather than raw checkpoint counts.
    """
    cum = cumulative_distances(points)
    geo_total = cum[-1] if cum else 0.0
    if geo_total <= 0:
        raise ValueError("Route geometry has zero length")

    interval_m = interval_miles * METERS_PER_MILE
    targets = list(_frange(0.0, geo_total, interval_m))
    if geo_total - targets[-1] < 0.25 * interval_m and len(targets) > 1:
        targets[-1] = geo_total  # merge a tiny tail into the destination checkpoint
    else:
        targets.append(geo_total)

    # Provider distance/time are authoritative; geometry length only positions points.
    scale = (route.distance_m / geo_total) if route.distance_m > 0 else 1.0
    profile = route.time_profile or [(0.0, 0.0), (route.distance_m, route.duration_s)]

    boundaries = [0]
    for left, right in zip(targets, targets[1:]):
        boundaries.append(nearest_vertex_index(cum, (left + right) / 2))
    boundaries.append(len(points) - 1)

    checkpoints: list[Checkpoint] = []
    for seq, target in enumerate(targets):
        position, _ = point_at_distance(points, cum, target)
        prev_gap = target - targets[seq - 1] if seq > 0 else 0.0
        next_gap = targets[seq + 1] - target if seq + 1 < len(targets) else 0.0
        route_d = target * scale
        checkpoints.append(
            Checkpoint(
                sequence=seq,
                position=position,
                distance_m=route_d,
                offset_s=time_at_distance(profile, route_d),
                segment_m=(prev_gap + next_gap) / 2 * scale,
                path_start_index=boundaries[seq],
                path_end_index=max(boundaries[seq + 1], boundaries[seq]),
            )
        )
    return checkpoints


# --- Heatmap corridor grid -----------------------------------------------------------

def corridor_grid(
    paths: list[list[LatLng]],
    buffer_miles: float = 30.0,
    max_points: int = 250,
    initial_spacing_deg: float = 0.2,
) -> tuple[list[LatLng], float]:
    """Regular lat/lng grid covering only the area within `buffer_miles` of any path.

    Spacing starts fine and grows until the grid fits `max_points`, which keeps
    the Open-Meteo request volume bounded for very long trips.
    """
    samples: list[LatLng] = []
    for path in paths:
        if path:
            samples.extend(resample(path, cumulative_distances(path), 10 * METERS_PER_MILE))
    if not samples:
        return [], initial_spacing_deg

    buffer_m = buffer_miles * METERS_PER_MILE
    buffer_lat_deg = buffer_m / 111_320
    mid_lat = (min(s.lat for s in samples) + max(s.lat for s in samples)) / 2
    lng_per_lat = 1 / max(math.cos(math.radians(mid_lat)), 0.2)
    south = min(s.lat for s in samples) - buffer_lat_deg
    west = min(s.lng for s in samples) - buffer_lat_deg * lng_per_lat

    spacing = initial_spacing_deg
    while True:
        lat_step, lng_step = spacing, spacing * lng_per_lat
        cells: set[tuple[int, int]] = set()
        reach_i = math.ceil(buffer_lat_deg / lat_step)
        reach_j = math.ceil(buffer_lat_deg * lng_per_lat / lng_step)
        for s in samples:
            ci = round((s.lat - south) / lat_step)
            cj = round((s.lng - west) / lng_step)
            cos_lat = math.cos(math.radians(s.lat))
            for i in range(ci - reach_i, ci + reach_i + 1):
                dlat = (south + i * lat_step - s.lat) * 111_320
                for j in range(cj - reach_j, cj + reach_j + 1):
                    if (i, j) in cells:
                        continue
                    dlng = (west + j * lng_step - s.lng) * 111_320 * cos_lat
                    if dlat * dlat + dlng * dlng <= buffer_m * buffer_m:
                        cells.add((i, j))
        if len(cells) <= max_points:
            grid = [LatLng(south + i * lat_step, west + j * lng_step) for i, j in sorted(cells)]
            return grid, spacing
        spacing *= 1.2
