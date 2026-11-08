import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# Safe by default: DEBUG is off unless DJANGO_DEBUG=true (backend/.env sets it for local work).
DEBUG = _env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me" if DEBUG else "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (required when DJANGO_DEBUG is not true).")
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Behind Railway's HTTPS proxy: trust its forwarded-protocol header so Django knows requests are secure.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "truckroute.urls"
WSGI_APPLICATION = "truckroute.wsgi.application"
ASGI_APPLICATION = "truckroute.asgi.application"

DATABASES: dict = {}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truckroute",
        "TIMEOUT": 15 * 60,
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "api.exceptions.api_exception_handler",
}

CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# --- External providers -------------------------------------------------------
FREEROUTE_API_KEY = os.environ.get("FREEROUTE_API_KEY", "").strip()
FREEROUTE_BASE_URL = os.environ.get(
    "FREEROUTE_BASE_URL", "https://api.maps.freeroute.org/v1"
).rstrip("/")
FREEROUTE_PROFILE = os.environ.get("FREEROUTE_PROFILE", "driving-car").strip()

# Countries trips may start/end in (ISO-3 codes as returned by the geocoder). Empty = anywhere.
ALLOWED_COUNTRY_CODES = [c.upper() for c in _env_list("ALLOWED_COUNTRY_CODES", "USA")]

# Type-ahead top-up for the place dropdown (FreeRoute only matches whole words). Empty = off.
AUTOCOMPLETE_FALLBACK_URL = os.environ.get("AUTOCOMPLETE_FALLBACK_URL", "https://photon.komoot.io/api/").strip()
OPEN_METEO_BASE_URL = os.environ.get(
    "OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast"
)
HTTP_USER_AGENT = "TruckWeatherRouter/1.0"
TRUCK_DURATION_FACTOR = float(os.environ.get("TRUCK_DURATION_FACTOR", "1.10"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"httpx": {"level": "WARNING"}},
}
