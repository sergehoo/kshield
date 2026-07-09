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
    path("rfid/", include("devices.urls_rfid")),
]

from devices.views import BadgePDFDownloadView, BadgeThumbnailView

# Django admin réservé aux superusers — caché en prod (uniquement accessible
# si DEBUG=True ou si l'utilisateur appelle directement /django-admin/).
# Toutes les actions métier doivent passer par le back-office custom KAYDAN
# (templates/administration/*.html).
admin.site.site_header = "KAYDAN SHIELD — Admin technique"
admin.site.site_title = "KAYDAN admin"
admin.site.index_title = "Administration interne (superuser uniquement)"

urlpatterns = [
    # ───── Monitoring Prometheus (à scraper par /metrics) ─────
    # django-prometheus expose métriques HTTP + DB + cache automatiquement.
    # Métriques business custom dans core/metrics.py (mises à jour par Celery).
    path("", include("django_prometheus.urls")),  # → /metrics
    # On déplace l'admin Django vers /django-admin/ (path obscur réservé aux DBA).
    # /admin/ sera capturé par administration.urls et redirigera vers la home.
    path("django-admin/", admin.site.urls),
    # Endpoints healthcheck publics — pas d'auth, pas de log spam
    # (utilisés par Docker HEALTHCHECK et Kubernetes liveness/readiness)
    path("healthz", __import__("core.views", fromlist=["healthz"]).healthz, name="healthz"),
    path("readyz",  __import__("core.views", fromlist=["readyz"]).readyz,   name="readyz"),
    # Endpoints ADMS ZKTeco-compatibles à la racine (les terminaux AI810 /
    # AiFace hardcodent le path /iclock/cdata sans préfixe /api/v1/).
    # Ces routes délèguent à ZkAdmsWebhookView du module devices.
    path("iclock/cdata",
         __import__("devices.views", fromlist=["ZkAdmsWebhookView"]).ZkAdmsWebhookView.as_view(),
         name="iclock-cdata"),
    path("iclock/getrequest",
         __import__("devices.views", fromlist=["IclockGetRequestView"]).IclockGetRequestView.as_view(),
         name="iclock-getrequest"),
    path("iclock/devicecmd",
         __import__("devices.views", fromlist=["IclockDeviceCmdView"]).IclockDeviceCmdView.as_view(),
         name="iclock-devicecmd"),
    # Catch-all pour firmwares whitebox qui push sur /pub/api* (AiFace ai810 & co)
    # Accepte tout, log body brut, répond OK pour empêcher les retry en boucle.
    path("pub/api",
         __import__("devices.views", fromlist=["PubApiCatchAllView"]).PubApiCatchAllView.as_view(),
         name="pub-api-root"),
    path("pub/api/<path:subpath>",
         __import__("devices.views", fromlist=["PubApiCatchAllView"]).PubApiCatchAllView.as_view(),
         name="pub-api-sub"),
    # Endpoints directs badges (servis hors API)
    path("badges/<int:pk>/pdf/",       BadgePDFDownloadView.as_view(), name="badge-pdf"),
    path("badges/<int:pk>/thumbnail/", BadgeThumbnailView.as_view(),   name="badge-thumbnail"),
    # Back-office KAYDAN (administration)
    path("", include("administration.urls")),
    # ───── SSO Keycloak (OIDC) ─────
    path("sso/", include("sso.urls")),
    path("api/sso/", include("sso.api_urls")),
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

    # Django Debug Toolbar — monter ses URLs uniquement si l'app est installée
    if "debug_toolbar" in settings.INSTALLED_APPS:
        try:
            import debug_toolbar
            urlpatterns = [
                path("__debug__/", include("debug_toolbar.urls")),
                *urlpatterns,
            ]
        except ImportError:
            pass
