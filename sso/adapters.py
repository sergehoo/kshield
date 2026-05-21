"""Adapters pour intégrer Keycloak côté server-to-server (admin API).

Permet à KAYDAN SHIELD de :
- créer un user Keycloak quand on crée un User local (optionnel)
- désactiver un user Keycloak quand on désactive le User local
- forcer un logout global d'un user (admin tools)

Utilise le token client_credentials grant du client `kaydan-shield-api`.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _admin_token() -> str | None:
    """Récupère un access_token admin via client_credentials grant.

    Le client `kaydan-shield-api` doit être configuré avec :
      - access type: confidential
      - service accounts enabled
      - role realm-management:realm-admin (ou plus restreint)
    """
    cache_key = "sso:admin_token"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        import requests
        url = settings.OIDC_OP_TOKEN_ENDPOINT
        resp = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": getattr(settings, "OIDC_RP_CLIENT_ID", ""),
            "client_secret": getattr(settings, "OIDC_RP_CLIENT_SECRET", ""),
        }, timeout=5)
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            cache.set(cache_key, token, 50)  # un peu moins que 60s
        return token
    except Exception:
        logger.exception("admin_token fetch failed")
        return None


def disable_keycloak_user(subject: str) -> bool:
    """Désactive un user dans Keycloak via l'admin API."""
    token = _admin_token()
    if not token:
        return False
    try:
        import requests
        base = settings.KEYCLOAK_BASE_URL.rstrip("/")
        realm = settings.KEYCLOAK_REALM
        url = f"{base}/admin/realms/{realm}/users/{subject}"
        resp = requests.put(url, json={"enabled": False},
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=5)
        return resp.status_code in (204, 200)
    except Exception:
        logger.exception("disable_keycloak_user failed")
        return False


def force_logout_keycloak_user(subject: str) -> bool:
    """Force la déconnexion globale d'un user (toutes ses sessions)."""
    token = _admin_token()
    if not token:
        return False
    try:
        import requests
        base = settings.KEYCLOAK_BASE_URL.rstrip("/")
        realm = settings.KEYCLOAK_REALM
        url = f"{base}/admin/realms/{realm}/users/{subject}/logout"
        resp = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                              timeout=5)
        return resp.status_code in (204, 200)
    except Exception:
        logger.exception("force_logout_keycloak_user failed")
        return False
