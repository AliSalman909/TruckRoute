"""Turning what the user typed (or picked) into a Place, and the rules around it.

Three ways a location can arrive:
1. Picked from the autocomplete dropdown: the frontend sends the label *and* its
   coordinates, so we use exactly that place (no guessing).
2. Typed coordinates ("41.88, -87.63"): used as-is.
3. Free text ("Springfield"): we search and take the best match inside the
   allowed countries. The chosen label is returned so the UI can show it.

Every path enforces the country restriction (settings.ALLOWED_COUNTRY_CODES):
text results carry a country code; coordinates are reverse-geocoded to find theirs.
"""

from __future__ import annotations

import re
from dataclasses import replace

import httpx
from django.conf import settings

from ..exceptions import RoutingError
from .models import LatLng, Place

SEARCH_FETCH_LIMIT = 15  # over-fetch so country filtering still leaves enough results
MAX_SUGGESTIONS = 10

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

COUNTRY_NAMES = {"USA": "the United States", "CAN": "Canada", "MEX": "Mexico"}


# --- country rules -----------------------------------------------------------------------

def allowed_countries() -> list[str]:
    return settings.ALLOWED_COUNTRY_CODES


def area_name() -> str:
    codes = allowed_countries()
    return " / ".join(COUNTRY_NAMES.get(c, c) for c in codes) if codes else "anywhere"


def country_allowed(code: str) -> bool:
    codes = allowed_countries()
    return not codes or code.upper() in codes


async def _check_point(provider, p: LatLng, what: str) -> Place | None:
    """Coordinates carry no country, so ask the geocoder where they are (reverse geocoding).

    A bounding box is not enough: southern Ontario sits inside any box around the
    contiguous US. Returns the nearest address (for a friendly label), or None when
    unrestricted.
    """
    if not (-90 <= p.lat <= 90 and -180 <= p.lng <= 180):
        raise RoutingError(f"{what} coordinates are out of range.", status=422)
    if not allowed_countries():
        return None
    nearest = await provider.reverse_geocode(p)
    if nearest is None:
        raise RoutingError(f"{what} isn't near any known address (open water?).", status=422)
    if not country_allowed(nearest.country_code):
        raise RoutingError(
            f"{what} ({nearest.label}) is outside the supported area ({area_name()}).", status=422
        )
    return nearest


# --- suggestions & resolution ---------------------------------------------------------------

async def suggest(provider, query: str, limit: int = 5, prefix_search=None) -> list[Place]:
    """Autocomplete: places matching `query`, inside the allowed countries.

    FreeRoute results come first. FreeRoute only matches whole words, so when it
    returns too few, `prefix_search` (Photon) tops the list up with places whose
    names *start with* the text ("Springf" -> Springfield).
    """
    limit = min(limit, MAX_SUGGESTIONS)
    results = [p for p in await provider.search_places(query, SEARCH_FETCH_LIMIT) if country_allowed(p.country_code)]
    if len(results) < limit and prefix_search is not None:
        for p in await prefix_search(query, SEARCH_FETCH_LIMIT):
            if country_allowed(p.country_code) and not any(_same_place(p, r) for r in results):
                results.append(p)
    return results[:limit]


def _same_place(a: Place, b: Place) -> bool:
    """Same label, or within ~5 km (the two geocoders put city centres slightly apart)."""
    close = abs(a.point.lat - b.point.lat) < 0.05 and abs(a.point.lng - b.point.lng) < 0.05
    return a.label.casefold() == b.label.casefold() or close


async def resolve(provider, query: str, location: LatLng | None, what: str) -> tuple[Place, str | None]:
    """The place to route from/to, plus an optional warning for the user.

    `what` is "Origin" or "Destination", used in messages.
    """
    query = query.strip()
    if location is not None:  # picked from the dropdown: use it exactly, but still check the area
        await _check_point(provider, location, what)
        return Place(label=query, point=location, source="suggestion"), None

    match = _COORD_RE.match(query)
    if match:
        point = LatLng(float(match.group(1)), float(match.group(2)))
        nearest = await _check_point(provider, point, what)
        label = f"Near {nearest.label}" if nearest else f"{point.lat:.5f}, {point.lng:.5f}"
        return Place(label=label, point=point, source="coordinates"), None

    results = await provider.search_places(query, SEARCH_FETCH_LIMIT)
    if not results:
        raise RoutingError(f"Could not find a location for '{query}'.", status=422)
    allowed = [p for p in results if country_allowed(p.country_code)]
    if not allowed:
        raise RoutingError(
            f"'{results[0].label}' is outside the supported area ({area_name()}).", status=422
        )
    best = replace(allowed[0], source="search")
    warning = None
    if allowed[0] is not results[0]:
        warning = (
            f"{what} '{query}' best matched {results[0].label}, which is outside {area_name()}; "
            f"using {best.label} instead."
        )
    return best, warning


async def suggest_places(query: str, limit: int) -> dict:
    """Entry point for GET /api/v1/places/."""
    from . import photon, routing  # local import: routing is the provider factory

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0)) as client:
        provider = routing.get_provider(client)
        results = await suggest(
            provider, query, limit, prefix_search=lambda q, n: photon.search_prefix(client, q, n)
        )
    return {
        "status": "SUCCESS",
        "query": query,
        "allowed_area": area_name(),
        "results": [{"label": p.label, **p.point.to_dict()} for p in results],
    }
