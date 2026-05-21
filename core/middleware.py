"""Middlewares core : tenant context + CSP / security headers."""
from __future__ import annotations

from django.conf import settings


class TenantContextMiddleware:
    """Attache request.tenant si le user est authentifié (via FK tenant sur User)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            request.tenant = getattr(user, "tenant", None)
        # fallback header (utile pour terminaux IoT signés)
        if request.tenant is None:
            header_code = request.headers.get("X-Tenant")
            if header_code:
                from .models import Tenant

                request.tenant = Tenant.objects.filter(code=header_code, is_active=True).first()
        return self.get_response(request)


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
