"""Décorateurs SSO pour les vues fonction-based."""
from __future__ import annotations

from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect


def sso_login_required(view_func):
    """Comme @login_required mais redirige vers /sso/login/ si SSO activé."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        from django.conf import settings
        if getattr(settings, "SSO_ENABLED", False):
            return redirect("sso:login")
        return redirect("admin-login")
    return wrapper


def sso_perm_required(perm_code: str):
    """Permission RBAC requise (utilise accounts.rbac.user_has_permission)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("admin-login")
            from accounts.rbac import user_has_permission
            if not user_has_permission(request.user, perm_code):
                return JsonResponse(
                    {"error": "Permission refusée", "required": perm_code},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
