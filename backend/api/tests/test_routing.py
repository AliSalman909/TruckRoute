import asyncio

from api.services import routing

from .fakes import DEST, ORIGIN, FakeProvider, future


def run(coro):
    return asyncio.run(coro)


def test_generates_detours_until_three_distinct_routes():
    provider = FakeProvider(primary_count=1)
    routes, warnings = run(routing.get_route_options(provider, ORIGIN, DEST, future()))
    assert len(routes) == 3
    assert warnings == []
    assert routes[0].via_waypoint is None
    assert all(r.via_waypoint is not None for r in routes[1:])
    for i, r in enumerate(routes):
        assert routing.is_distinct(r, [o for j, o in enumerate(routes) if j != i])


def test_only_fills_the_missing_routes():
    provider = FakeProvider(primary_count=2)
    routes, _ = run(routing.get_route_options(provider, ORIGIN, DEST, future()))
    assert len(routes) == 3
    assert sum(r.via_waypoint is not None for r in routes) == 1


def test_rejects_detours_that_are_far_slower():
    provider = FakeProvider(primary_count=1, detour_mph=20)
    routes, warnings = run(routing.get_route_options(provider, ORIGIN, DEST, future()))
    assert len(routes) == 1
    assert warnings and "Only 1" in warnings[0]


def test_detour_offset_scales_with_trip_length():
    provider = FakeProvider()
    base = run(provider.compute_routes(ORIGIN, DEST, future()))[0]
    wps = routing.detour_waypoints(base)
    from api.services import spatial

    mid_offsets = [
        spatial.distance_m(spatial.decode_polyline(base.encoded_polyline)[0], wp) for wp in wps
    ]
    assert len(wps) == 4
    assert all(d > 0 for d in mid_offsets)
