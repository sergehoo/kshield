"""Middleware résolvant le tenant courant à partir du JWT ou du header."""
from __future__ import annotations


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
