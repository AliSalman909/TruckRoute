import pytest

from api.services import spatial
from api.services.models import LatLng, RouteCandidate

GOOGLE_EXAMPLE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"  # from Google's polyline docs


def test_decode_matches_reference():
    pts = spatial.decode_polyline(GOOGLE_EXAMPLE)
    assert pts == [LatLng(38.5, -120.2), LatLng(40.7, -120.95), LatLng(43.252, -126.453)]


def test_encode_round_trip():
    pts = spatial.decode_polyline(GOOGLE_EXAMPLE)
    assert spatial.encode_polyline(pts) == GOOGLE_EXAMPLE


def test_geodesic_distance_chicago_denver():
    d_mi = spatial.distance_m(LatLng(41.8781, -87.6298), LatLng(39.7392, -104.9903)) / spatial.METERS_PER_MILE
    assert d_mi == pytest.approx(920, abs=5)


def test_simplify_removes_collinear_points_only():
    line = [LatLng(40.0, -100.0 + i * 0.01) for i in range(50)]
    kink = line + [LatLng(40.5, -99.5)]
    assert len(spatial.simplify(line)) == 2
    assert len(spatial.simplify(kink)) == 3


def _straight_route(miles: float, hours: float, profile=None) -> tuple[RouteCandidate, list[LatLng]]:
    start = LatLng(40.0, -100.0)
    end = spatial.project(start, 90, miles * spatial.METERS_PER_MILE)
    pts = [start] + [spatial.project(start, 90, f * miles * spatial.METERS_PER_MILE) for f in (0.25, 0.5, 0.75)] + [end]
    dist = miles * spatial.METERS_PER_MILE
    route = RouteCandidate(
        encoded_polyline=spatial.encode_polyline(pts),
        distance_m=dist,
        duration_s=hours * 3600,
        summary="test",
        time_profile=profile or [(0.0, 0.0), (dist, hours * 3600)],
    )
    return route, pts


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_cover_route(interval):
    route, pts = _straight_route(miles=103, hours=2)
    cps = spatial.build_checkpoints(route, pts, interval)
    miles = [c.distance_m / spatial.METERS_PER_MILE for c in cps]
    assert miles[0] == 0
    assert miles[-1] == pytest.approx(103, abs=0.01)
    gaps = [b - a for a, b in zip(miles, miles[1:])]
    assert all(g == pytest.approx(interval) for g in gaps[:-1])
    assert 0 < gaps[-1] < 1.25 * interval  # a short tail merges into the destination
    # Segment attribution adds up to the full route length.
    assert sum(c.segment_m for c in cps) == pytest.approx(route.distance_m, rel=1e-6)
    assert [c.sequence for c in cps] == list(range(len(cps)))


def test_tiny_tail_merges_into_destination():
    route, pts = _straight_route(miles=52, hours=1)
    cps = spatial.build_checkpoints(route, pts, 25)
    # 0, 25, 52 (the 2-mile tail after 50 merges into the destination checkpoint)
    assert [round(c.distance_m / spatial.METERS_PER_MILE) for c in cps] == [0, 25, 52]


def test_eta_follows_step_profile_not_average_speed():
    miles = 100
    dist = miles * spatial.METERS_PER_MILE
    # First half slow (1.5 h), second half fast (0.5 h).
    profile = [(0.0, 0.0), (dist / 2, 5400.0), (dist, 7200.0)]
    route, pts = _straight_route(miles=miles, hours=2, profile=profile)
    cps = spatial.build_checkpoints(route, pts, 50)
    assert [round(c.offset_s) for c in cps] == [0, 5400, 7200]


def test_normalize_profile_scales_to_route_totals():
    out = spatial.normalize_profile([(100, 10), (200, 30)], distance_m=400, duration_s=60)
    assert out == [(0.0, 0.0), (200.0, 20.0), (400.0, 60.0)]


def test_corridor_grid_respects_point_cap():
    path = [LatLng(41.88, -87.63), LatLng(39.74, -104.99)]
    grid, spacing = spatial.corridor_grid([path], buffer_miles=30, max_points=250)
    assert 0 < len(grid) <= 250
    assert spacing >= 0.2
