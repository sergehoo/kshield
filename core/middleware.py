"""Middlewares core : tenant context + CSP / security headers + slow request log."""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import connection

_perf_logger = logging.getLogger("kshield.perf")


class SlowRequestLoggerMiddleware:
    """Logue chaque requête > SLOW_THRESHOLD_MS (default 1000 ms).

    Log format : ``METHOD PATH → status (Xms, N queries, Yms SQL)``
    Sert à identifier les vues qui rament sans avoir à installer django-debug-toolbar
    en production.

    Le seuil est configurable via ``settings.SLOW_REQUEST_THRESHOLD_MS`` (int).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = getattr(settings, "SLOW_REQUEST_THRESHOLD_MS", 1000)

    def __call__(self, request):
        start = time.monotonic()
        query_count_start = len(connection.queries)
        response = self.get_response(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        # DEBUG=True : connection.queries est peuplé. En prod, il est vide.
        query_count = len(connection.queries) - query_count_start
        sql_time_ms = 0
        if query_count > 0 and settings.DEBUG:
            sql_time_ms = int(sum(float(q.get("time", 0)) for q in
                                    connection.queries[query_count_start:]) * 1000)

        if duration_ms >= self.threshold_ms:
            # Exclut les healthchecks pour ne pas polluer
            if request.path in ("/healthz", "/readyz", "/metrics"):
                return response
            _perf_logger.warning(
                "[SLOW %dms] %s %s → %s (queries=%d, sql=%dms)",
                duration_ms, request.method, request.path,
                response.status_code, query_count, sql_time_ms,
            )
        # Header X-Response-Time pour debug côté navigateur
        response["X-Response-Time-ms"] = str(duration_ms)
        return response


class TenantContextMiddleware:
    """Attache request.tenant et peuple le thread-local pour get_current_tenant().

    Détection en cascade :
      1. ``user.tenant`` si user authentifié (cas standard back-office)
      2. Header HTTP ``X-Tenant: <code>`` (IoT signé, app mobile)
      3. Sous-domaine ``<tenant_code>.kaydanshield.com`` (multi-org SaaS)
      4. Fallback : Kaydan (mono-tenant historique)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .services import clear_current_tenant, set_current_tenant
        request.tenant = self._resolve_tenant(request)
        set_current_tenant(request.tenant)
        try:
            response = self.get_response(request)
        finally:
            # Nettoie le thread-local — on est en pool de workers gunicorn,
            # un thread peut servir un request d'un autre tenant juste après.
            clear_current_tenant()
        return response

    def _resolve_tenant(self, request):
        from .models import Tenant

        # 1) User authentifié
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            t = getattr(user, "tenant", None)
            if t is not None:
                return t

        # 2) Header explicite (IoT, M2M)
        header_code = request.headers.get("X-Tenant")
        if header_code:
            t = Tenant.objects.filter(code=header_code, is_active=True).first()
            if t:
                return t

        # 3) Sous-domaine — extrait le 1er segment si DEEP_DOMAIN matches.
        # Format attendu : <tenant>.kaydanshield.com
        host = (request.get_host() or "").lower().split(":")[0]
        from django.conf import settings
        base = getattr(settings, "TENANT_BASE_DOMAIN", "kaydanshield.com")
        if host.endswith("." + base):
            sub = host[: -(len(base) + 1)]
            # On ignore les sous-domaines techniques fonctionnels
            if sub not in ("api", "ws", "minio", "minio-console",
                           "adminer", "www"):
                # Le 1er segment peut être un code tenant
                first = sub.split(".")[0]
                if first:
                    t = Tenant.objects.filter(code=first, is_active=True).first()
                    if t:
                        return t

        # 4) Fallback : mono-tenant historique
        from .services import get_kaydan_tenant
        return get_kaydan_tenant()


# ---------------------------------------------------------------------------
# Content Security Policy + headers de durcissement complémentaires
# ---------------------------------------------------------------------------
_DEFAULT_CSP = {
    "default-src": "'self'",
    # Alpine.js x-data/x-show évalue des expressions JS → unsafe-eval requis.
    # unpkg + jsdelivr : Alpine, Lucide, face-api.js + ses modèles TF.
    "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net",
    "style-src": "'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "style-src-elem": "'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "img-src": "'self' data: blob: https://*.tile.openstreetmap.org https://*.basemaps.cartocdn.com",
    "font-src": "'self' data: https://fonts.gstatic.com",
    # connect-src : fetch des poids face-api (jsdelivr) + maps unpkg + WS realtime
    "connect-src": "'self' wss: ws: https://unpkg.com https://cdn.jsdelivr.net",
    "frame-ancestors": "'none'",
    "form-action": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",
}


class SecurityHeadersMiddleware:
    """Pose Content-Security-Policy + Permissions-Policy + Cross-Origin-* sur chaque réponse.

    La CSP par défaut couvre Tailwind/Alpine inline, Leaflet, tuiles OSM.
    Override possible via ``settings.CSP_DIRECTIVES`` (dict directive→source-list).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        directives = getattr(settings, "CSP_DIRECTIVES", _DEFAULT_CSP) or _DEFAULT_CSP
        self._csp = "; ".join(f"{k} {v}" for k, v in directives.items())
        self._report_only = getattr(settings, "CSP_REPORT_ONLY", False)

    def __call__(self, request):
        response = self.get_response(request)
        header = "Content-Security-Policy-Report-Only" if self._report_only else "Content-Security-Policy"
        response.setdefault(header, self._csp)
        response.setdefault(
            "Permissions-Policy",
            "camera=(self), microphone=(), geolocation=(self), payment=()",
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
