"""FreeRouteProvider against a mock transport replaying the live API's response shapes."""

import asyncio
import json

import httpx
import pytest
from django.core.cache import cache

from api.exceptions import RoutingError
from api.services import spatial
from api.services.models import LatLng
from api.services.routing import FreeRouteProvider

BASE = "https://fr.test/v1"
CHICAGO = [-87.66063, 41.87897]
DENVER = [-104.98486, 39.73924]
OAK_PARK = [-87.7845, 41.8850]  # ~10 km from Chicago: short enough for alternatives
CHI, DEN, OAK = (LatLng(c[1], c[0]) for c in (CHICAGO, DENVER, OAK_PARK))


def geocode_response(coords, label):
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": coords},
                      "properties": {"label": label, "countrycode": "USA"}}],
    }


def route_feature(coords, steps):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "summary": {"distance": sum(s["distance"] for s in steps), "duration": sum(s["duration"] for s in steps)},
            "segments": [{"distance": 0, "duration": 0, "steps": steps}],
            "way_points": [0, len(coords) - 1],
        },
    }


LONG_ROUTE = route_feature(
    [CHICAGO, [-93.6, 41.6], DENVER],
    [
        {"distance": 2000.0, "duration": 300.0, "name": "South Federal Street"},
        {"distance": 570000.0, "duration": 19000.0, "name": "I 80 Express"},
        {"distance": 224000.0, "duration": 8000.0, "name": "Ronald Reagan Memorial Tollway, I 88, IL 110"},
        {"distance": 286000.0, "duration": 10000.0, "name": "I 76"},
        {"distance": 300.0, "duration": 20.0, "name": "-"},
    ],
)


class Recorder:
    """Mock transport handler: routes requests to canned responses and records them."""

    def __init__(self, directions=None):
        self.requests: list[httpx.Request] = []
        self.directions = directions or (lambda body: httpx.Response(200, json={"features": [LONG_ROUTE]}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/geocode/search"):
            q = request.url.params["q"]
            table = {"Chicago, IL": CHICAGO, "Denver, CO": DENVER, "Oak Park, IL": OAK_PARK}
            if q not in table:
                return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
            return httpx.Response(200, json=geocode_response(table[q], q))
        return self.directions(json.loads(request.content))

    def bodies(self):
        return [json.loads(r.content) for r in self.requests if "/directions/" in r.url.path]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def run(recorder, coro_fn):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
            return await coro_fn(FreeRouteProvider(client, BASE, "fro_test", "driving-car"))
    return asyncio.run(go())


def test_long_trip_parses_geojson_and_skips_alternatives():
    rec = Recorder()
    routes = run(rec, lambda p: p.compute_routes(CHI, DEN, None))
    route = routes[0]

    body = rec.bodies()[0]
    assert "alternative_routes" not in body  # >100 km: FreeRoute would answer 500
    assert body["coordinates"] == [CHICAGO, DENVER]  # [lng, lat]
    assert body["radiuses"] == [5000, 5000]
    assert rec.requests[0].headers["Authorization"] == "Bearer fro_test"
    assert rec.requests[-1].url.path == "/v1/directions/driving-car"

    assert route.distance_m == pytest.approx(1_082_300)
    assert route.duration_s == pytest.approx(37_320)
    assert route.summary == "I 80 · I 76"  # top roads by distance, highway refs extracted
    assert spatial.decode_polyline(route.encoded_polyline)[0] == LatLng(41.87897, -87.66063)
    assert route.time_profile[-1] == (pytest.approx(route.distance_m), pytest.approx(route.duration_s))


def test_short_trip_requests_alternatives_and_retries_without_on_500():
    def directions(body):
        if "alternative_routes" in body:
            return httpx.Response(500, json={"statusCode": 500, "message": "Internal server error"})
        return httpx.Response(200, json={"features": [LONG_ROUTE]})

    rec = Recorder(directions)
    routes = run(rec, lambda p: p.compute_routes(CHI, OAK, None))
    bodies = rec.bodies()
    assert bodies[0]["alternative_routes"]["target_count"] == 3
    assert "alternative_routes" not in bodies[1]
    assert len(routes) == 1


def test_detour_waypoint_snaps_with_large_radius_and_unroutable_returns_empty():
    rec = Recorder(lambda body: httpx.Response(500, json={"statusCode": 500}))
    via = LatLng(42.9, -96.5)
    routes = run(rec, lambda p: p.compute_routes(CHI, DEN, None, via=via))
    body = rec.bodies()[0]
    assert body["coordinates"][1] == [-96.5, 42.9]
    assert body["radiuses"] == [5000, 25000, 5000]
    assert routes == []


def test_primary_route_failure_is_a_routing_error():
    rec = Recorder(lambda body: httpx.Response(500, json={"statusCode": 500}))
    with pytest.raises(RoutingError) as err:
        run(rec, lambda p: p.compute_routes(CHI, DEN, None))
    assert err.value.status == 422


def test_search_places_parses_labels_and_country_codes():
    rec = Recorder()
    places = run(rec, lambda p: p.search_places("Chicago, IL", 5))
    assert rec.requests[0].url.params["q"] == "Chicago, IL"
    assert rec.requests[0].url.params["limit"] == "5"
    assert places[0].label == "Chicago, IL"
    assert places[0].point == LatLng(41.87897, -87.66063)
    assert places[0].country_code == "USA"


def test_unknown_place_returns_no_results():
    assert run(Recorder(), lambda p: p.search_places("Atlantis", 5)) == []


def test_search_results_are_cached_across_requests():
    rec = Recorder()
    run(rec, lambda p: p.search_places("Chicago, IL", 5))
    run(rec, lambda p: p.search_places("chicago, il", 5))
    assert len(rec.requests) == 1


@pytest.mark.parametrize("status, expected", [(429, 503), (401, 502), (400, 422)])
def test_http_errors_map_to_routing_errors(status, expected):
    rec = Recorder(lambda body: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(RoutingError) as err:
        run(rec, lambda p: p.compute_routes(CHI, DEN, None))
    assert err.value.status == expected


def test_reverse_geocode_returns_country_and_none_over_water():
    def handler(request):
        if request.url.path.endswith("/geocode/reverse"):
            if request.url.params["lat"] == "35.0":
                return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
            return httpx.Response(200, json={"type": "FeatureCollection", "features": [{
                "type": "Feature", "geometry": {"type": "Point", "coordinates": [-79.3795, 43.65]},
                "properties": {"label": "11 Adelaide Street West, Toronto, ON, Canada", "countrycode": "CAN"}}]})
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            p = FreeRouteProvider(client, BASE, "fro_test", "driving-car")
            return await p.reverse_geocode(LatLng(43.65, -79.38)), await p.reverse_geocode(LatLng(35.0, -40.0))

    toronto, ocean = asyncio.run(go())
    assert toronto.country_code == "CAN"
    assert ocean is None
