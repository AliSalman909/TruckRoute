"""Orchestration: routes -> checkpoints -> weather -> risk -> ranking -> JSON.

The view layer calls `analyze_routes` / `corridor_weather_grid` and returns
whatever they produce. All third-party I/O happens inside one
httpx.AsyncClient, so route and weather requests run concurrently.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import httpx
from django.conf import settings

from ..exceptions import ForecastHorizonError, RoutingError
from . import places, ranking, routing, spatial, weather
from .models import Checkpoint, LatLng, RouteCandidate, RoutePlan, WeatherSample
from .risk import RiskAssessment, assess, assess_sample

SAFETY_SHIFT_STEP_H = 3
SAFETY_SHIFT_MAX_H = 24
HTTP_TIMEOUT = httpx.Timeout(25.0, connect=10.0)


@dataclass
class CheckpointResult:
    checkpoint: Checkpoint
    eta: datetime
    sample: WeatherSample
    assessment: RiskAssessment


@dataclass
class RouteEvaluation:
    plan: RoutePlan
    checkpoints: list[CheckpointResult]
    score: ranking.RouteScore


# --- Entry point: route analysis ------------------------------------------------------

async def analyze_routes(
    origin: str,
    destination: str,
    departure_time: datetime,
    load_weight: int,
    interval_miles: int,
    origin_location: dict | None = None,
    destination_location: dict | None = None,
) -> dict:
    departure = departure_time.astimezone(timezone.utc)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        provider = routing.get_provider(client)

        # 1. Turn text (or a picked suggestion) into places, both at once.
        (origin_place, origin_note), (dest_place, dest_note) = await asyncio.gather(
            places.resolve(provider, origin, _latlng(origin_location), "Origin"),
            places.resolve(provider, destination, _latlng(destination_location), "Destination"),
        )
        if spatial.distance_m(origin_place.point, dest_place.point) < 1_000:
            raise RoutingError(
                f"Origin and destination both resolve to {origin_place.label}; choose two different places.",
                status=422,
            )
        warnings = [note for note in (origin_note, dest_note) if note]

        # 2. Routes between the two resolved points.
        candidates, route_warnings = await routing.get_route_options(
            provider, origin_place.point, dest_place.point, departure
        )
        warnings += route_warnings
        plans = [
            _build_plan(f"route_{i + 1}", _apply_truck_factor(c), interval_miles)
            for i, c in enumerate(candidates)
        ]

        longest_s = max(p.route.duration_s for p in plans)
        trip_end = departure + timedelta(seconds=longest_s)
        horizon = weather.forecast_horizon()
        if trip_end > horizon:
            raise ForecastHorizonError(
                "Weather forecasts only extend to "
                f"{horizon:%b %d, %H:%M} UTC; choose an earlier departure so the trip ends before then.",
                details={"forecast_horizon": _iso(horizon)},
            )
        max_shift_h = min(SAFETY_SHIFT_MAX_H, int((horizon - trip_end).total_seconds() // 3600))
        series = await weather.fetch_hourly(
            client,
            [cp.position for p in plans for cp in p.checkpoints],
            departure,
            trip_end + timedelta(hours=max_shift_h),
        )

    def evaluate(shift_h: int) -> list[RouteEvaluation]:
        start = departure + timedelta(hours=shift_h)
        return [_evaluate_plan(p, series, start, load_weight) for p in plans]

    evaluations = evaluate(0)
    ranked = ranking.rank_routes([e.score for e in evaluations])
    rank_of = {s.route_id: i + 1 for i, s in enumerate(ranked)}
    recommended = ranked[0]
    all_unsafe = not recommended.is_viable

    safe_departure = None
    if all_unsafe:
        found = ranking.find_safe_departure(
            lambda h: [e.score for e in evaluate(h)], max_shift_h, SAFETY_SHIFT_STEP_H
        )
        if found:
            shift_h, best = found
            safe_departure = {
                "departure_time": _iso(departure + timedelta(hours=shift_h)),
                "delay_hours": shift_h,
                "route_id": best.route_id,
                "risk_summary": best.counts_dict(),
                "risk_miles": best.miles_dict(),
            }
        else:
            warnings.append(
                f"No departure within the next {max_shift_h} h avoids No Travel conditions on any route."
            )

    first = plans[0].route
    return {
        "status": "SUCCESS",
        "all_routes_unsafe": all_unsafe,
        "suggested_departure_time": safe_departure["departure_time"] if safe_departure else None,
        "safe_departure": safe_departure,
        "recommended_route_id": recommended.route_id,
        "recommendation_reason": ranking.explain_recommendation(ranked),
        "routing_provider": provider.name,
        "request": {
            "origin": origin,
            "destination": destination,
            "departure_time": _iso(departure),
            "load_weight": load_weight,
            "interval_miles": interval_miles,
        },
        # What we understood each place as. Coordinates are the route's snapped start/end,
        # so map pins sit exactly on the drawn line.
        "origin": {
            **origin_place.to_dict(),
            **(first.start or plans[0].geometry[0]).to_dict(),
            "query": origin,
        },
        "destination": {
            **dest_place.to_dict(),
            **(first.end or plans[0].geometry[-1]).to_dict(),
            "query": destination,
        },
        "allowed_area": places.area_name(),
        "forecast_horizon": _iso(horizon),
        "warnings": warnings,
        "routes": [
            _route_to_dict(e, departure, rank_of[e.plan.id], e.plan.id == recommended.route_id)
            for e in evaluations
        ],
    }


def _latlng(location: dict | None) -> LatLng | None:
    return LatLng(location["lat"], location["lng"]) if location else None


def _apply_truck_factor(route: RouteCandidate) -> RouteCandidate:
    f = settings.TRUCK_DURATION_FACTOR
    if f == 1.0:
        return route
    return replace(
        route,
        duration_s=route.duration_s * f,
        time_profile=[(d, t * f) for d, t in route.time_profile],
    )


def _build_plan(route_id: str, route: RouteCandidate, interval_miles: int) -> RoutePlan:
    # ~15 m simplification cuts geometry 70-90% with no visible change on the map.
    geometry = spatial.simplify(spatial.decode_polyline(route.encoded_polyline))
    return RoutePlan(
        id=route_id,
        route=route,
        geometry=geometry,
        checkpoints=spatial.build_checkpoints(route, geometry, interval_miles),
    )


def _evaluate_plan(
    plan: RoutePlan,
    series: dict[weather.LocationKey, weather.HourlySeries],
    departure: datetime,
    load_weight: int,
) -> RouteEvaluation:
    results = []
    for cp in plan.checkpoints:
        eta = departure + timedelta(seconds=cp.offset_s)
        sample = series[weather.location_key(cp.position)].sample(eta)
        results.append(CheckpointResult(cp, eta, sample, assess_sample(sample, load_weight)))
    score = ranking.score_route(
        plan.id,
        plan.route.duration_s,
        [(r.assessment.level, r.checkpoint.segment_m) for r in results],
    )
    return RouteEvaluation(plan, results, score)


# --- Entry point: heatmap grid -----------------------------------------------------------

async def corridor_weather_grid(
    polylines: list[str], start_time: datetime, load_weight: int, hours: int
) -> dict:
    paths = [spatial.decode_polyline(p) for p in polylines]
    grid, spacing = spatial.corridor_grid(paths)

    start = weather.floor_hour(start_time)
    end = min(start + timedelta(hours=hours), weather.forecast_horizon())
    if end < start:
        raise ForecastHorizonError("The requested start time is beyond the forecast horizon.")
    count = int((end - start).total_seconds() // 3600) + 1

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        series = await weather.fetch_hourly(client, grid, start, end)

    points = []
    for p in grid:
        s = series[weather.location_key(p)]
        i0 = s.index_for(start)
        wind = s.wind[i0 : i0 + count]
        rain = s.rain[i0 : i0 + count]
        snow = s.snow[i0 : i0 + count]
        points.append(
            {
                "lat": round(p.lat, 4),
                "lng": round(p.lng, 4),
                "wind": [round(v, 1) for v in wind],
                "rain": [round(v, 2) for v in rain],
                "snow": [round(v, 2) for v in snow],
                "risk": [int(assess(w, r, sn, load_weight).level) for w, r, sn in zip(wind, rain, snow)],
            }
        )

    return {
        "status": "SUCCESS",
        "start_time": _iso(start),
        "times": [_iso(start + timedelta(hours=i)) for i in range(count)],
        "spacing_deg": round(spacing, 3),
        "points": points,
    }


# --- Serialisation -------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _route_to_dict(e: RouteEvaluation, departure: datetime, rank: int, recommended: bool) -> dict:
    route, score = e.plan.route, e.score
    return {
        "id": e.plan.id,
        "rank": rank,
        "is_recommended": recommended,
        "is_viable": score.is_viable,
        "summary": route.summary,
        "is_generated_detour": route.via_waypoint is not None,
        "total_distance_miles": round(route.distance_m / spatial.METERS_PER_MILE, 1),
        "total_duration_mins": round(route.duration_s / 60),
        "departure_time": _iso(departure),
        "arrival_time": _iso(departure + timedelta(seconds=route.duration_s)),
        "risk_summary": score.counts_dict(),
        "risk_miles": score.miles_dict(),
        "avg_risk_score": round(score.avg_risk, 2),
        "max_risk_level": score.max_level.label,
        "encoded_polyline": spatial.encode_polyline(e.plan.geometry),
        "geometry": [p.to_dict() for p in e.plan.geometry],
        "checkpoints": [
            {
                "sequence": r.checkpoint.sequence,
                "lat": round(r.checkpoint.position.lat, 5),
                "lng": round(r.checkpoint.position.lng, 5),
                "eta": _iso(r.eta),
                "distance_from_origin_miles": round(r.checkpoint.distance_m / spatial.METERS_PER_MILE, 1),
                "segment_miles": round(r.checkpoint.segment_m / spatial.METERS_PER_MILE, 1),
                "path_range": [r.checkpoint.path_start_index, r.checkpoint.path_end_index],
                "weather": r.sample.to_dict(),
                "risk_level": r.assessment.level.label,
                "risk_reasons": list(r.assessment.reasons),
            }
            for r in e.checkpoints
        ],
    }
