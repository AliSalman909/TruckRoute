from asgiref.sync import async_to_sync
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AnalyzeRoutesRequestSerializer,
    PlacesQuerySerializer,
    WeatherGridRequestSerializer,
)
from .services.analysis import analyze_routes, corridor_weather_grid
from .services.places import suggest_places


class AnalyzeRoutesView(APIView):
    def post(self, request):
        serializer = AnalyzeRoutesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = async_to_sync(analyze_routes)(**serializer.validated_data)
        return Response(result)


class WeatherGridView(APIView):
    def post(self, request):
        serializer = WeatherGridRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = async_to_sync(corridor_weather_grid)(**serializer.validated_data)
        return Response(result)


class PlacesView(APIView):
    """Autocomplete suggestions for the origin/destination inputs."""

    def get(self, request):
        serializer = PlacesQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = async_to_sync(suggest_places)(serializer.validated_data["q"], serializer.validated_data["limit"])
        return Response(result)


class HealthView(APIView):
    def get(self, request):
        from django.conf import settings

        return Response(
            {
                "status": "OK",
                "routing_provider": "freeroute",
                "profile": settings.FREEROUTE_PROFILE,
                "api_key_configured": bool(settings.FREEROUTE_API_KEY),
            }
        )
