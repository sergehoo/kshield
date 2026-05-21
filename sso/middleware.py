"""Middleware SSO — refresh token automatique + invalidation back-channel."""
from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


class SSOTokenRefreshMiddleware:
    """Renouvelle silencieusement l'access_token Keycloak quand il approche
    de l'expiration (5 min). Évite à l'utilisateur d'être déconnecté en
    plein milieu de session.

    Stocke `access_token`, `refresh_token`, `expires_at` dans la session
    Django (set par mozilla-django-oidc à la fin du callback).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "SSO_ENABLED", False):
            return self.get_response(request)
        try:
            self._maybe_refresh(request)
        except Exception:
            logger.debug("SSO refresh échoué (non bloquant)", exc_info=True)
        return self.get_response(request)

    def _maybe_refresh(self, request):
        sess = request.session
        exp = sess.get("oidc_id_token_expiration", 0) or sess.get("oidc_expires_at", 0)
        refresh = sess.get("oidc_refresh_token") or sess.get("refresh_token")
        if not exp or not refresh:
            return
        # Renouvelle si moins de 5 minutes restantes
        if exp - time.time() > 300:
            return
        try:
            import requests
            url = settings.OIDC_OP_TOKEN_ENDPOINT
            client_id = settings.OIDC_RP_CLIENT_ID
            client_secret = getattr(settings, "OIDC_RP_CLIENT_SECRET", "")
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
            }
            if client_secret:
                data["client_secret"] = client_secret
            resp = requests.post(url, data=data, timeout=5)
            if resp.status_code == 200:
                tok = resp.json()
                sess["oidc_access_token"] = tok.get("access_token")
                sess["oidc_refresh_token"] = tok.get("refresh_token", refresh)
                sess["oidc_expires_at"] = int(time.time()) + tok.get("expires_in", 300)
                sess.modified = True
            else:
                logger.warning("Refresh token rejeté par Keycloak: %s", resp.status_code)
        except Exception:
            logger.exception("Refresh token request failed")
