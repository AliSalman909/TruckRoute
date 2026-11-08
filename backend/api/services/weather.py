"""Open-Meteo hourly forecasts, fetched concurrently in batches.

Design points:
* One request carries up to 50 locations (Open-Meteo accepts comma-separated lists).
* Each location fetches a whole time window (departure through the last possible
  arrival, plus room for later departure times). Delayed-departure suggestions
  then need no extra API calls; we just read a later hour from the same series.
* Locations are rounded to 0.01 deg (~1 km), so overlapping routes share requests,
  and results are cached for 15 minutes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from django.conf import settings
from django.core.cache import cache

from ..exceptions import WeatherServiceError
from .models import LatLng, WeatherSample

log = logging.getLogger(__name__)

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
CHUNK_SIZE = 50
MAX_CONCURRENCY = 4
FORECAST_DAYS = 16
CACHE_TTL_S = 15 * 60
MAX_ATTEMPTS = 3

LocationKey = tuple[float, float]


@dataclass(frozen=True)
class HourlySeries:
    start: datetime
    wind: tuple[float, ...]
    gust: tuple[float, ...]
    rain: tuple[float, ...]
    snow: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.wind)

    def index_for(self, when: datetime) -> int:
        idx = round((when - self.start).total_seconds() / 3600)
        return min(max(idx, 0), len(self) - 1)

    def sample(self, when: datetime) -> WeatherSample:
        i = self.index_for(when)
        return WeatherSample(
            wind_mph=self.wind[i],
            gust_mph=self.gust[i],
            rain_in_hr=self.rain[i],
            snow_in_hr=self.snow[i],
            time=self.start + timedelta(hours=i),
        )


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def ceil_hour(dt: datetime) -> datetime:
    floored = floor_hour(dt)
    return floored if floored == dt else floored + timedelta(hours=1)


def forecast_horizon(now: datetime | None = None) -> datetime:
    """Last forecast hour Open-Meteo can return (23:00 UTC on the 16th forecast day)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=FORECAST_DAYS) - timedelta(hours=1)


def location_key(p: LatLng) -> LocationKey:
    return (round(p.lat, 2), round(p.lng, 2))


def _cache_key(key: LocationKey, start: datetime, end: datetime) -> str:
    return f"om:{key[0]:.2f}:{key[1]:.2f}:{start:%Y%m%d%H}:{end:%Y%m%d%H}"


async def fetch_hourly(
    client: httpx.AsyncClient, locations: list[LatLng], start: datetime, end: datetime
) -> dict[LocationKey, HourlySeries]:
    """Hourly series for each (rounded) location covering [start, end] inclusive."""
    start, end = floor_hour(start), ceil_hour(end)
    keys = list(dict.fromkeys(location_key(p) for p in locations))

    result: dict[LocationKey, HourlySeries] = {}
    missing: list[LocationKey] = []
    for key in keys:
        cached = await cache.aget(_cache_key(key, start, end))
        if cached is not None:
            result[key] = cached
        else:
            missing.append(key)

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(chunk: list[LocationKey]) -> dict[LocationKey, HourlySeries]:
        async with semaphore:
            return await _fetch_chunk(client, chunk, start, end)

    chunks = [missing[i : i + CHUNK_SIZE] for i in range(0, len(missing), CHUNK_SIZE)]
    for fetched in await asyncio.gather(*(run(c) for c in chunks)):
        for key, series in fetched.items():
            result[key] = series
            await cache.aset(_cache_key(key, start, end), series, CACHE_TTL_S)
    log.info("Weather: %d locations (%d cached, %d requests)", len(keys), len(keys) - len(missing), len(chunks))
    return result


async def _fetch_chunk(
    client: httpx.AsyncClient, keys: list[LocationKey], start: datetime, end: datetime
) -> dict[LocationKey, HourlySeries]:
    params = {
        "latitude": ",".join(f"{k[0]:.2f}" for k in keys),
        "longitude": ",".join(f"{k[1]:.2f}" for k in keys),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",  # also switches snowfall to inches
        "timezone": "GMT",
        "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
    }
    last_error = "unknown error"
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = await client.get(settings.OPEN_METEO_BASE_URL, params=params)
        except httpx.HTTPError as exc:
            last_error = str(exc) or exc.__class__.__name__
        else:
            if resp.status_code == 200:
                payload = resp.json()
                items = payload if isinstance(payload, list) else [payload]
                return {key: _parse_series(item) for key, item in zip(keys, items)}
            if resp.status_code == 400:
                reason = resp.json().get("reason", "bad request")
                raise WeatherServiceError(f"Open-Meteo rejected the request: {reason}", status=502)
            last_error = f"HTTP {resp.status_code}"
        if attempt + 1 < MAX_ATTEMPTS:
            await asyncio.sleep(1.5 * (attempt + 1))
    raise WeatherServiceError(f"Weather service unavailable ({last_error}).", status=503)


def _parse_series(item: dict) -> HourlySeries:
    hourly = item["hourly"]

    def values(name: str) -> tuple[float, ...]:
        return tuple(float(v) if v is not None else 0.0 for v in hourly.get(name, []))

    rain = tuple(r + s for r, s in zip(values("rain"), values("showers")))
    return HourlySeries(
        start=datetime.fromisoformat(hourly["time"][0]).replace(tzinfo=timezone.utc),
        wind=values("wind_speed_10m"),
        gust=values("wind_gusts_10m"),
        rain=rain,
        snow=values("snowfall"),
    )
