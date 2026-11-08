from django.urls import path

from .views import AnalyzeRoutesView, HealthView, PlacesView, WeatherGridView

urlpatterns = [
    path("analyze-routes/", AnalyzeRoutesView.as_view(), name="analyze-routes"),
    path("weather-grid/", WeatherGridView.as_view(), name="weather-grid"),
    path("places/", PlacesView.as_view(), name="places"),
    path("health/", HealthView.as_view(), name="health"),
]
