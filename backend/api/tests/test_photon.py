"""Photon prefix search: response parsing, labels, and failing quietly."""

import asyncio

import httpx
import pytest
from django.core.cache import cache

from api.services import photon

SAMPLE = {"features": [
    {"geometry": {"coordinates": [-89.65, 39.80]},
     "properties": {"name": "Springfield", "state": "Illinois", "countrycode": "US"}},
    {"geometry": {"coordinates": [-79.38, 43.65]},
     "properties": {"name": "Toronto", "state": "Ontario", "country": "Canada", "countrycode": "CA"}},
]}


@pytest.fixture(autouse=True)
def setup(settings):
    cache.clear()
    settings.AUTOCOMPLETE_FALLBACK_URL = "https://photon.test/api/"


def run(handler):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await photon.search_prefix(client, "Spr", 5)
    return asyncio.run(go())


def test_parses_labels_and_converts_country_codes():
    places = run(lambda request: httpx.Response(200, json=SAMPLE))
    assert places[0].label == "Springfield, IL, USA"
    assert places[0].country_code == "USA"
    assert places[1].label == "Toronto, Ontario, Canada"
    assert places[1].country_code == "CAN"


def test_outage_returns_empty_list_instead_of_failing():
    assert run(lambda request: httpx.Response(503)) == []


def test_disabled_when_url_is_empty(settings):
    settings.AUTOCOMPLETE_FALLBACK_URL = ""
    assert run(lambda request: pytest.fail("should not be called")) == []
