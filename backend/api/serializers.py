"""Request validation. Responses are built in services.analysis."""

from datetime import timedelta, timezone

from django.utils import timezone as dj_timezone
from rest_framework import serializers

MAX_DEPARTURE_DAYS_AHEAD = 14
MAX_LOAD_LB = 120_000


class LatLngSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)


class AnalyzeRoutesRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200, trim_whitespace=True)
    destination = serializers.CharField(max_length=200, trim_whitespace=True)
    # Sent when the user picked a suggestion from the dropdown: use exactly this place.
    origin_location = LatLngSerializer(required=False, allow_null=True, default=None)
    destination_location = LatLngSerializer(required=False, allow_null=True, default=None)
    departure_time = serializers.DateTimeField(default_timezone=timezone.utc)
    load_weight = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate_departure_time(self, value):
        now = dj_timezone.now()
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure time cannot be in the past.")
        if value > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {MAX_DEPARTURE_DAYS_AHEAD} days (weather forecast range)."
            )
        return value

    def validate(self, attrs):
        if attrs["origin"].casefold() == attrs["destination"].casefold():
            raise serializers.ValidationError({"destination": "Destination must differ from origin."})
        return attrs


class PlacesQuerySerializer(serializers.Serializer):
    """GET /api/v1/places/?q=Spring&limit=5"""

    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=10, default=5)


class WeatherGridRequestSerializer(serializers.Serializer):
    polylines = serializers.ListField(
        child=serializers.CharField(max_length=200_000, trim_whitespace=False),
        min_length=1,
        max_length=5,
    )
    start_time = serializers.DateTimeField(default_timezone=timezone.utc)
    load_weight = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    hours = serializers.IntegerField(min_value=1, max_value=48, default=48)
