"""Permissions DRF spécifiques KAYDAN SHIELD."""
from rest_framework import permissions

from accounts.models import APIKey


class IsAuthenticatedOrAPIKey(permissions.BasePermission):
    """Autorise soit un user authentifié (JWT/session), soit une APIKey via HMAC."""

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        if isinstance(getattr(request, "auth", None), APIKey):
            return True
        return False
