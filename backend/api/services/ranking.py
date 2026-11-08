"""Route scoring, ranking and safer-departure search.

Ranking follows the brief's priority order, measured in route *miles* (each
checkpoint represents the miles around it), not checkpoint counts:

    0. Viable routes (no No Travel miles) before non-viable ones
    1. Fewest Severe miles
    2. Fewest High miles
    3. Lowest average risk (mile-weighted, 0=Low ... 4=No Travel)
    4. Shortest travel time

Miles are compared to the nearest mile and average risk to 0.05. Without that,
noise-level differences in the earlier criteria (0.01 of a risk point) would
decide the result before travel time is ever considered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .risk import RiskLevel
from .spatial import METERS_PER_MILE

AVG_RISK_TOLERANCE = 0.05


@dataclass
class RouteScore:
    route_id: str
    duration_s: float
    miles: dict[RiskLevel, float] = field(default_factory=dict)
    counts: dict[RiskLevel, int] = field(default_factory=dict)
    avg_risk: float = 0.0
    max_level: RiskLevel = RiskLevel.LOW

    @property
    def is_viable(self) -> bool:
        return self.counts.get(RiskLevel.NO_TRAVEL, 0) == 0

    def counts_dict(self) -> dict[str, int]:
        return {lvl.key: self.counts.get(lvl, 0) for lvl in reversed(RiskLevel)}

    def miles_dict(self) -> dict[str, float]:
        return {lvl.key: round(self.miles.get(lvl, 0.0), 1) for lvl in reversed(RiskLevel)}


def score_route(route_id: str, duration_s: float, samples: list[tuple[RiskLevel, float]]) -> RouteScore:
    """`samples` is one (risk level, segment metres) pair per checkpoint."""
    miles = {lvl: 0.0 for lvl in RiskLevel}
    counts = {lvl: 0 for lvl in RiskLevel}
    weighted = total = 0.0
    for level, segment_m in samples:
        seg_mi = segment_m / METERS_PER_MILE
        miles[level] += seg_mi
        counts[level] += 1
        weighted += int(level) * seg_mi
        total += seg_mi
    if total > 0:
        avg = weighted / total
    else:
        avg = sum(int(lvl) for lvl, _ in samples) / max(len(samples), 1)
    return RouteScore(
        route_id=route_id,
        duration_s=duration_s,
        miles=miles,
        counts=counts,
        avg_risk=avg,
        max_level=max((lvl for lvl, _ in samples), default=RiskLevel.LOW),
    )


def _bucket(value: float, size: float) -> int:
    return round(value / size)


def ranking_key(score: RouteScore) -> tuple:
    return (
        0 if score.is_viable else 1,
        _bucket(score.miles[RiskLevel.NO_TRAVEL], 1.0),
        _bucket(score.miles[RiskLevel.SEVERE], 1.0),
        _bucket(score.miles[RiskLevel.HIGH], 1.0),
        _bucket(score.avg_risk, AVG_RISK_TOLERANCE),
        score.duration_s,
    )


def rank_routes(scores: list[RouteScore]) -> list[RouteScore]:
    return sorted(scores, key=ranking_key)


def explain_recommendation(ranked: list[RouteScore]) -> str:
    """Name the criterion that separated the winner from the runner-up."""
    if not ranked:
        return ""
    best = ranked[0]
    if not best.is_viable:
        return (
            "Every route crosses No Travel conditions at this departure time; "
            "the route with the least exposure is highlighted."
        )
    if len(ranked) == 1:
        return "Only one viable route is available."
    other = ranked[1]
    if not other.is_viable:
        return "The only route(s) without No Travel conditions."
    kb, ko = ranking_key(best), ranking_key(other)
    sev, high = RiskLevel.SEVERE, RiskLevel.HIGH
    if kb[2] != ko[2]:
        return f"Fewest Severe-risk miles ({best.miles[sev]:.0f} vs {other.miles[sev]:.0f})."
    if kb[3] != ko[3]:
        return f"Fewest High-risk miles ({best.miles[high]:.0f} vs {other.miles[high]:.0f})."
    if kb[4] != ko[4]:
        return f"Lowest average weather risk ({best.avg_risk:.2f} vs {other.avg_risk:.2f} on a 0-4 scale)."
    diff_min = (other.duration_s - best.duration_s) / 60
    if diff_min < 1:
        return "Equivalent weather risk and travel time to the next option."
    return f"Same weather exposure as the next option and {diff_min:.0f} min faster."


def find_safe_departure(
    evaluate: Callable[[int], list[RouteScore]], max_shift_h: int, step_h: int = 3
) -> tuple[int, RouteScore] | None:
    """First later departure (in `step_h` increments) where at least one route is viable."""
    for shift in range(step_h, max_shift_h + 1, step_h):
        ranked = rank_routes(evaluate(shift))
        if ranked and ranked[0].is_viable:
            return shift, ranked[0]
    return None
