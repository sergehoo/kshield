"""KAYDAN SHIELD — URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import TokenRefreshView

api_v1 = [
    path("auth/", include("accounts.urls")),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("core/", include("core.urls")),
    path("sites/", include("sites.urls")),
    path("employees/", include("employees.urls")),
    path("ouvriers/", include("ouvriers.urls")),
    path("visitors/", include("visitors.urls")),
    path("devices/", include("devices.urls")),
    path("access/", include("access_control.urls")),
    path("attendance/", include("attendance.urls")),
    path("antifraud/", include("antifraud.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
    path("reports/", include("reports.urls")),
    path("mobile/", include("mobile_sync.urls")),
    path("ai/", include("ai_assistant.urls")),
]

from devices.views import BadgePDFDownloadView, BadgeThumbnailView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Endpoints directs badges (servis hors API)
    path("badges/<int:pk>/pdf/",       BadgePDFDownloadView.as_view(), name="badge-pdf"),
    path("badges/<int:pk>/thumbnail/", BadgeThumbnailView.as_view(),   name="badge-thumbnail"),
    # Back-office KAYDAN (administration)
    path("", include("administration.urls")),
    path("api/v1/", include(api_v1)),
    # OpenAPI / docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Médias uploadés (logos filiales, photos, badges PDF/PNG, etc.)
# En prod c'est nginx qui sert /media/ via alias.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
