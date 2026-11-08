"""Prefix ("type-ahead") place search via Photon (https://photon.komoot.io).

Why this exists: FreeRoute's geocoder only matches whole words, so "Springf" or
"Chicag" return nothing while the user is still typing. Photon is a free,
keyless geocoder built for autocomplete on the same OpenStreetMap data.

It is used ONLY to top up dropdown suggestions. Whatever the user picks is still
checked by FreeRoute (reverse geocoding) before any routing happens.
Set AUTOCOMPLETE_FALLBACK_URL= (empty) in .env to switch it off.
"""

from __future__ import annotations

import hashlib
import logging

import httpx
from django.conf import settings
from django.core.cache import cache

from .models import LatLng, Place

log = logging.getLogger(__name__)

CACHE_S = 24 * 3600

# Photon returns ISO-2 country codes; the rest of the app uses ISO-3 (as FreeRoute does).
ISO2_TO_ISO3 = {"US": "USA", "CA": "CAN", "MX": "MEX", "GB": "GBR", "FR": "FRA", "DE": "DEU"}

US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def _label(props: dict, iso3: str) -> str:
    """Match FreeRoute's style: 'Springfield, IL, USA'."""
    name = props.get("name", "")
    state = props.get("state", "")
    if iso3 == "USA":
        return ", ".join(x for x in (name, US_STATES.get(state, state), "USA") if x)
    return ", ".join(x for x in (name, state, props.get("country", "")) if x)


async def search_prefix(client: httpx.AsyncClient, query: str, limit: int) -> list[Place]:
    """Cities/towns whose names start with what the user has typed. Never raises."""
    url = settings.AUTOCOMPLETE_FALLBACK_URL
    if not url:
        return []
    cache_key = "photon:" + hashlib.sha1(f"{query.strip().casefold()}|{limit}".encode()).hexdigest()
    cached = await cache.aget(cache_key)
    if cached is not None:
        return cached
    try:
        resp = await client.get(
            url,
            params={"q": query, "limit": limit, "layer": "city", "lang": "en"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=8.0,
        )
        resp.raise_for_status()
        features = resp.json().get("features") or []
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Photon autocomplete unavailable: %s", exc)
        return []  # suggestions are a convenience; FreeRoute results still show

    places = []
    for f in features:
        props = f.get("properties", {})
        lng, lat = f["geometry"]["coordinates"][:2]
        iso2 = (props.get("countrycode") or "").upper()
        iso3 = ISO2_TO_ISO3.get(iso2, iso2)
        places.append(Place(label=_label(props, iso3), point=LatLng(float(lat), float(lng)), country_code=iso3))
    await cache.aset(cache_key, places, CACHE_S)
    return places
