import pytest

from api.services.risk import RiskLevel as R
from api.services.risk import assess, classify_load, classify_rain, classify_snow, classify_wind


@pytest.mark.parametrize(
    "mph, expected",
    [(0, R.LOW), (24.9, R.LOW), (25, R.MODERATE), (34.9, R.MODERATE), (35, R.HIGH),
     (44.9, R.HIGH), (45, R.SEVERE), (54.9, R.SEVERE), (55, R.NO_TRAVEL), (80, R.NO_TRAVEL)],
)
def test_wind_bands(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rain, expected",
    [(0.0, R.LOW), (0.09, R.LOW), (0.10, R.MODERATE), (0.24, R.MODERATE), (0.25, R.HIGH),
     (0.49, R.HIGH), (0.50, R.SEVERE), (1.00, R.SEVERE), (1.01, R.NO_TRAVEL)],
)
def test_rain_bands(rain, expected):
    assert classify_rain(rain) == expected


@pytest.mark.parametrize(
    "snow, expected",
    [(0.0, R.LOW), (0.49, R.LOW), (0.5, R.MODERATE), (1.0, R.HIGH), (1.99, R.HIGH),
     (2.0, R.SEVERE), (3.0, R.SEVERE), (3.01, R.NO_TRAVEL)],
)
def test_snow_bands(snow, expected):
    assert classify_snow(snow) == expected


@pytest.mark.parametrize(
    "wind, load, expected",
    [
        (55, 0, R.NO_TRAVEL),          # >=55 mph: No Travel for any load
        (50, 30_000, R.LOW),           # boundary: rule is strictly > 30,000 lb
        (50, 30_001, R.NO_TRAVEL),
        (40, 40_000, R.LOW),
        (40, 40_001, R.SEVERE),
        (30, 80_000, R.LOW),           # load rules only apply at >=35 mph
    ],
)
def test_load_rules(wind, load, expected):
    assert classify_load(wind, load) == expected


def test_assess_takes_worst_factor_and_explains_it():
    result = assess(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0, load_lb=45_000)
    assert result.level == R.SEVERE  # weather says High, load rule escalates to Severe
    assert result.reasons == ("Wind 40 mph with 45,000 lb load → Severe",)


def test_light_load_in_strong_wind_uses_weather_table_only():
    assert assess(wind_mph=50, rain_in_hr=0, snow_in_hr=0, load_lb=20_000).level == R.SEVERE
    assert assess(wind_mph=50, rain_in_hr=0, snow_in_hr=0, load_lb=35_000).level == R.NO_TRAVEL


def test_low_risk_has_no_reasons():
    assert assess(5, 0, 0, 10_000).reasons == ()
