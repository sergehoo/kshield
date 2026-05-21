"""Helpers SSO — JWKS cache, claims extraction, role mapping."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def sso_enabled() -> bool:
    return bool(getattr(settings, "SSO_ENABLED", False))


def get_jwks() -> dict:
    """Récupère et met en cache les clés publiques JWKS de Keycloak.

    Cache 1 h (Keycloak rotate les clés rarement). En cas d'échec on retourne
    le cache existant pour ne pas casser tous les login DRF en même temps.
    """
    cache_key = "sso:jwks"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        import requests
        url = getattr(settings, "OIDC_OP_JWKS_ENDPOINT", "")
        if not url:
            return {"keys": []}
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        cache.set(cache_key, data, 3600)
        return data
    except Exception:
        logger.exception("JWKS fetch failed")
        return cached or {"keys": []}


def decode_jwt(token: str, audience: str | None = None) -> dict[str, Any]:
    """Décode et valide un JWT signé par Keycloak via JWKS."""
    import jwt
    from jwt import PyJWKClient

    jwks_url = getattr(settings, "OIDC_OP_JWKS_ENDPOINT", "")
    if not jwks_url:
        raise jwt.InvalidTokenError("JWKS endpoint non configuré")

    jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    signing_key = jwks_client.get_signing_key_from_jwt(token).key
    decoded = jwt.decode(
        token, signing_key, algorithms=["RS256"],
        audience=audience or getattr(settings, "OIDC_RP_CLIENT_ID", None),
        options={
            "verify_exp": True,
            "verify_iss": True,
        },
        issuer=getattr(settings, "OIDC_OP_ISSUER", None),
    )
    return decoded


def extract_user_claims(claims: dict[str, Any]) -> dict:
    """Normalise les claims OIDC vers un dict User KAYDAN."""
    return {
        "subject": claims.get("sub", ""),
        "email": (claims.get("email") or "").lower(),
        "first_name": claims.get("given_name", ""),
        "last_name": claims.get("family_name", ""),
        "preferred_username": claims.get("preferred_username", ""),
        "email_verified": bool(claims.get("email_verified", False)),
        "issuer": claims.get("iss", ""),
        # rôles realm Keycloak
        "realm_roles": (claims.get("realm_access") or {}).get("roles", []),
        # rôles client
        "client_roles": list(_iter_client_roles(claims)),
        # groupes (si mapper "groups" configuré dans Keycloak)
        "groups": claims.get("groups", []),
        # provenance fédération si présente
        "federation": claims.get("federationLink") or claims.get("identity_provider", ""),
    }


def _iter_client_roles(claims: dict[str, Any]):
    rc = claims.get("resource_access") or {}
    client_id = getattr(settings, "OIDC_RP_CLIENT_ID", "")
    if client_id and client_id in rc:
        for r in rc[client_id].get("roles") or []:
            yield r


def hash_pin(pin: str, salt: str = "") -> str:
    """PBKDF2 pour hasher un PIN à 4-6 chiffres pour le login offline."""
    if not pin:
        return ""
    salt = salt or getattr(settings, "SECRET_KEY", "kshield")[:16]
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), salt.encode(), 50_000,
    ).hex()
