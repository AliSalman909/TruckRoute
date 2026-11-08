"""Place resolution rules: suggestions, picked locations, typed coordinates, country restriction."""

import asyncio

import pytest

from api.exceptions import RoutingError
from api.services import places
from api.services.models import LatLng, Place

from .fakes import FakeProvider


def resolve(query, location=None, what="Origin"):
    return asyncio.run(places.resolve(FakeProvider(), query, location, what))


@pytest.fixture(autouse=True)
def us_only(settings):
    settings.ALLOWED_COUNTRY_CODES = ["USA"]


def test_free_text_uses_best_match_and_reports_its_label():
    place, warning = resolve("Springfield")
    assert place.label == "Springfield, MO, USA"  # the geocoder's first match
    assert place.source == "search"
    assert warning is None


def test_picked_suggestion_is_used_exactly_without_searching():
    provider = FakeProvider()
    il = LatLng(39.797, -89.646)
    place, _ = asyncio.run(places.resolve(provider, "Springfield, IL, USA", il, "Origin"))
    assert place.point == il
    assert place.label == "Springfield, IL, USA"
    assert place.source == "suggestion"
    assert provider.searches == []  # no guessing involved


def test_typed_coordinates_are_used_as_is():
    place, _ = resolve("41.5, -90.25")
    assert place.point == LatLng(41.5, -90.25)
    assert place.source == "coordinates"


def test_foreign_best_match_falls_back_to_allowed_country_with_warning():
    place, warning = resolve("Toronto")
    assert place.label == "Toronto, OH, USA"
    assert "Toronto, ON, Canada" in warning and "outside the United States" in warning


def test_place_with_no_allowed_match_is_rejected():
    with pytest.raises(RoutingError, match="outside the supported area"):
        resolve("Vancouver, BC")


def test_unknown_place_is_rejected():
    with pytest.raises(RoutingError, match="Could not find"):
        resolve("Atlantis")


@pytest.mark.parametrize("query", ["51.5, -0.12", "48.85, 2.35"])  # London, Paris
def test_coordinates_outside_us_are_rejected(query):
    with pytest.raises(RoutingError, match="outside the supported area"):
        resolve(query)


def test_picked_location_outside_us_is_rejected():
    with pytest.raises(RoutingError, match=r"Destination \(Toronto, ON, Canada\) is outside"):
        resolve("Somewhere", LatLng(43.65, -79.38), "Destination")


def test_alaska_and_hawaii_count_as_us():
    assert resolve("61.2, -149.9")[0].source == "coordinates"  # Anchorage
    assert resolve("21.3, -157.86")[0].source == "coordinates"  # Honolulu


def test_suggestions_are_filtered_to_allowed_countries():
    results = asyncio.run(places.suggest(FakeProvider(), "Toronto", 5))
    assert [p.label for p in results] == ["Toronto, OH, USA"]


def test_restriction_can_be_turned_off(settings):
    settings.ALLOWED_COUNTRY_CODES = []
    place, warning = resolve("Toronto")
    assert place.label == "Toronto, ON, Canada"
    assert warning is None
    assert resolve("51.5, -0.12")[0].source == "coordinates"


def test_coordinates_get_a_readable_label():
    assert resolve("41.5, -90.25")[0].label == "Near Moline, IL, USA"


def test_coordinates_in_open_water_are_rejected():
    with pytest.raises(RoutingError, match="open water"):
        resolve("35.0, -40.0")  # mid-Atlantic


# --- type-ahead top-up ------------------------------------------------------------------

def _prefix_search(found):
    async def search(query, limit):
        return found
    return search


def test_prefix_results_fill_in_when_whole_word_search_finds_nothing():
    found = [
        Place("Springfield, IL, USA", LatLng(39.8, -89.6), "USA"),
        Place("Springfield, ON, Canada", LatLng(42.8, -80.9), "CAN"),  # filtered: not US
    ]
    results = asyncio.run(places.suggest(FakeProvider(), "Springf", 5, prefix_search=_prefix_search(found)))
    assert [p.label for p in results] == ["Springfield, IL, USA"]


def test_prefix_results_skip_duplicates_of_whole_word_results():
    dup = [Place("Springfield, MO, USA", LatLng(37.21, -93.29), "USA")]  # ~1 km from the FreeRoute one
    results = asyncio.run(places.suggest(FakeProvider(), "Springfield", 5, prefix_search=_prefix_search(dup)))
    assert [p.label for p in results] == ["Springfield, MO, USA", "Springfield, IL, USA"]
