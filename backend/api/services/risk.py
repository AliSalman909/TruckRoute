"""Weather risk classification for a single checkpoint.

Thresholds (from the brief). Where the table's bands share an edge (e.g. rain
"0.10-0.25" and "0.25-0.50") the edge value belongs to the higher band, except
for the top band, which the brief marks as strictly greater than the edge
(rain > 1.00, snow > 3.00) or greater-or-equal (wind >= 55).

    Condition  Low      Moderate    High        Severe      No Travel
    Wind       <25      25-34       35-44       45-54       >=55 mph
    Rain       <0.10    0.10-0.25   0.25-0.50   0.50-1.00   >1.00 in/hr
    Snow       <0.5     0.5-1.0     1.0-2.0     2.0-3.0     >3.0 in/hr

Load rules (applied on top of the table, the worst result wins):
    wind >= 55                      -> No Travel for any load
    wind 45-54 and load > 30,000 lb -> No Travel
    wind 35-44 and load > 40,000 lb -> Severe
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .models import WeatherSample


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def key(self) -> str:
        return self.label.lower().replace(" ", "_")


_LABELS = {
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}

HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


def classify_wind(mph: float) -> RiskLevel:
    if mph >= 55:
        return RiskLevel.NO_TRAVEL
    if mph >= 45:
        return RiskLevel.SEVERE
    if mph >= 35:
        return RiskLevel.HIGH
    if mph >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(in_hr: float) -> RiskLevel:
    if in_hr > 1.00:
        return RiskLevel.NO_TRAVEL
    if in_hr >= 0.50:
        return RiskLevel.SEVERE
    if in_hr >= 0.25:
        return RiskLevel.HIGH
    if in_hr >= 0.10:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(in_hr: float) -> RiskLevel:
    if in_hr > 3.0:
        return RiskLevel.NO_TRAVEL
    if in_hr >= 2.0:
        return RiskLevel.SEVERE
    if in_hr >= 1.0:
        return RiskLevel.HIGH
    if in_hr >= 0.5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_load(wind_mph: float, load_lb: float) -> RiskLevel:
    if wind_mph >= 55:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= 45 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= 35 and load_lb > HEAVY_LOAD_SEVERE_LB:
        return RiskLevel.SEVERE
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: tuple[str, ...]


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> RiskAssessment:
    """Return the worst level across all conditions plus human-readable reasons."""
    factors = [
        (classify_wind(wind_mph), f"Wind {wind_mph:.0f} mph"),
        (classify_rain(rain_in_hr), f"Rain {rain_in_hr:.2f} in/hr"),
        (classify_snow(snow_in_hr), f"Snow {snow_in_hr:.2f} in/hr"),
        (
            classify_load(wind_mph, load_lb),
            f"Wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load",
        ),
    ]
    level = max(f[0] for f in factors)
    reasons: tuple[str, ...] = ()
    if level > RiskLevel.LOW:
        reasons = tuple(f"{text} → {lvl.label}" for lvl, text in factors if lvl == level)
    return RiskAssessment(level=level, reasons=reasons)


def assess_sample(sample: WeatherSample, load_lb: float) -> RiskAssessment:
    return assess(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, load_lb)
