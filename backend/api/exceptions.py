"""Domain errors and a DRF exception handler that renders one error envelope.

Every error response looks like:
    {"status": "ERROR", "error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging

from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger(__name__)


class ServiceError(Exception):
    code = "SERVICE_ERROR"
    default_status = 502

    def __init__(self, message: str, status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status or self.default_status
        self.details = details or {}


class RoutingError(ServiceError):
    code = "ROUTING_ERROR"


class WeatherServiceError(ServiceError):
    code = "WEATHER_ERROR"


class ForecastHorizonError(ServiceError):
    code = "FORECAST_UNAVAILABLE"
    default_status = 422


def _envelope(code: str, message: str, status: int, details: dict | None = None) -> Response:
    return Response(
        {"status": "ERROR", "error": {"code": code, "message": message, "details": details or {}}},
        status=status,
    )


def api_exception_handler(exc, context):
    if isinstance(exc, ServiceError):
        log.warning("%s: %s", exc.code, exc.message)
        return _envelope(exc.code, exc.message, exc.status, exc.details)

    if isinstance(exc, drf_exceptions.ValidationError):
        return _envelope("VALIDATION_ERROR", "Invalid request.", 400, exc.detail)

    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data.get("detail", "Request failed.") if isinstance(response.data, dict) else str(response.data)
        return _envelope(getattr(exc, "default_code", "ERROR").upper(), str(detail), response.status_code)

    log.exception("Unhandled error", exc_info=exc)
    return _envelope("INTERNAL_ERROR", "Unexpected server error.", 500)
