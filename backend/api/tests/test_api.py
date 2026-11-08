import pytest
from rest_framework.test import APIClient

from api.services import analysis, routing, weather

from .fakes import DEST, ORIGIN, FakeProvider, future, weather_stub

URL = "/api/v1/analyze-routes/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def fake_services(monkeypatch):
    monkeypatch.setattr(routing, "get_provider", lambda client: FakeProvider(primary_count=1))

    def install(**kwargs):
        monkeypatch.setattr(weather, "fetch_hourly", weather_stub(**kwargs))

    install()
    return install


def payload(**overrides):
    body = {
        "origin": "Omaha, NE",
        "destination": "Denver, CO",
        "departure_time": future().isoformat(),
        "load_weight": 45000,
        "interval_miles": 25,
    }
    body.update(overrides)
    return body


def test_validation_errors_use_error_envelope(client):
    resp = client.post(URL, payload(interval_miles=30, load_weight=-5), format="json")
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "ERROR"
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert set(body["error"]["details"]) == {"interval_miles", "load_weight"}


def test_rejects_past_departure(client):
    resp = client.post(URL, payload(departure_time="2020-01-01T00:00:00Z"), format="json")
    assert resp.status_code == 400
    assert "departure_time" in resp.json()["error"]["details"]


def test_success_payload_matches_contract(client, fake_services):
    resp = client.post(URL, payload(), format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "SUCCESS"
    assert body["all_routes_unsafe"] is False
    assert body["suggested_departure_time"] is None
    assert len(body["routes"]) == 3
    assert body["recommended_route_id"] in {r["id"] for r in body["routes"]}

    route = body["routes"][0]
    for key in ("id", "is_viable", "summary", "total_distance_miles", "total_duration_mins",
                "risk_summary", "risk_miles", "geometry", "checkpoints", "rank"):
        assert key in route
    assert set(route["risk_summary"]) == {"no_travel", "severe", "high", "moderate", "low"}
    cp = route["checkpoints"][1]
    assert set(cp["weather"]) >= {"wind_mph", "rain_in_hr", "snow_in_hr"}
    assert cp["risk_level"] == "Low"
    assert cp["eta"].endswith("Z")
    assert sorted(r["rank"] for r in body["routes"]) == [1, 2, 3]


def test_all_unsafe_suggests_later_departure(client, fake_services):
    # 60 mph wind for the first 7 forecast hours -> No Travel everywhere, then calm.
    fake_services(wind_by_hour={h: 60.0 for h in range(7)})
    resp = client.post(URL, payload(), format="json")
    body = resp.json()
    assert body["all_routes_unsafe"] is True
    assert all(not r["is_viable"] for r in body["routes"])
    assert body["safe_departure"]["delay_hours"] % 3 == 0
    assert body["suggested_departure_time"] == body["safe_departure"]["departure_time"]


def test_forecast_horizon_error(client, fake_services, monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(analysis.weather, "forecast_horizon", lambda now=None: future(0) + timedelta(hours=2))
    resp = client.post(URL, payload(), format="json")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "FORECAST_UNAVAILABLE"


# --- resolved places, picked suggestions, country restriction ---------------------------

def test_response_reports_how_each_place_was_understood(client, fake_services):
    body = client.post(URL, payload(), format="json").json()
    assert body["origin"]["label"] == "Omaha, NE, USA"
    assert body["origin"]["query"] == "Omaha, NE"
    assert body["origin"]["matched_by"] == "search"
    assert body["destination"]["label"] == "Denver, CO, USA"
    assert body["allowed_area"] == "the United States"


def test_picked_suggestion_skips_geocoding(client, fake_services):
    body = client.post(
        URL,
        payload(
            origin="My yard",  # not in the fake geocoder: would fail if it were searched
            origin_location={"lat": ORIGIN.lat, "lng": ORIGIN.lng},
            destination_location={"lat": DEST.lat, "lng": DEST.lng},
        ),
        format="json",
    ).json()
    assert body["status"] == "SUCCESS", body
    assert body["origin"]["label"] == "My yard"
    assert body["origin"]["matched_by"] == "suggestion"


def test_foreign_destination_is_rejected(client, fake_services):
    resp = client.post(URL, payload(destination="Vancouver, BC"), format="json")
    assert resp.status_code == 422
    assert "outside the supported area" in resp.json()["error"]["message"]


def test_invalid_picked_coordinates_fail_validation(client):
    resp = client.post(URL, payload(origin_location={"lat": 200, "lng": 0}), format="json")
    assert resp.status_code == 400
    assert "origin_location" in resp.json()["error"]["details"]


def test_places_endpoint_returns_filtered_suggestions(client, fake_services, settings):
    settings.AUTOCOMPLETE_FALLBACK_URL = ""  # keep the test offline (no Photon top-up)
    resp = client.get("/api/v1/places/", {"q": "Toronto"})
    assert resp.status_code == 200
    assert [r["label"] for r in resp.json()["results"]] == ["Toronto, OH, USA"]


def test_places_endpoint_requires_two_characters(client):
    resp = client.get("/api/v1/places/", {"q": "a"})
    assert resp.status_code == 400
