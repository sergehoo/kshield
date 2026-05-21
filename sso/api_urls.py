"""URLs API pour /api/sso/* — séparées de /sso/* (web)."""
from .urls import api_urlpatterns as urlpatterns  # noqa: F401

app_name = "sso_api"
