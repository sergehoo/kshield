"""KAYDAN SHIELD — Authentification HMAC pour terminaux IoT.

Schéma utilisé par les passerelles KAYDAN-EDGE et les lecteurs NFC fixes :
les requêtes vers les endpoints d'ingestion (par défaut /api/v1/access/scan/)
sont signées avec une clé API (`accounts.APIKey`).

En-têtes attendus :
    X-KShield-Key-Id      Public ID de la clé API.
    X-KShield-Timestamp   Epoch en secondes (UTF-8). Tolérance: API_KEY_CLOCK_SKEW_SEC.
    X-KShield-Signature   hex(HMAC-SHA256(key=secret_hash, msg=canonical_string)).

Canonical string :
    "{timestamp}\n{METHOD}\n{path}\n{sha256_hex(body)}"

`secret_hash` est la valeur stockée en base (`APIKey.secret_hash`), qui correspond à
SHA-256(secret_brut). Le client (passerelle) reçoit le secret brut UNE seule fois,
calcule lui-même `sha256(secret).hex()` côté device et l'utilise comme clé HMAC.
Le serveur lit `APIKey.secret_hash` directement et signe pareil — pas besoin de
stocker le secret en clair.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


HEADER_KEY_ID = "HTTP_X_KSHIELD_KEY_ID"
HEADER_TS = "HTTP_X_KSHIELD_TIMESTAMP"
HEADER_SIG = "HTTP_X_KSHIELD_SIGNATURE"


def canonical_string(timestamp: str, method: str, path: str, body: bytes) -> str:
    """Reconstruit la chaîne canonique signée par le client."""
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{timestamp}\n{method.upper()}\n{path}\n{body_hash}"


def sign(secret_hash: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    """Calcule la signature attendue (hex)."""
    msg = canonical_string(timestamp, method, path, body).encode("utf-8")
    return hmac.new(secret_hash.encode("utf-8"), msg, hashlib.sha256).hexdigest()


class HMACSignatureError(exceptions.AuthenticationFailed):
    pass


class HMACAPIKeyAuthentication(authentication.BaseAuthentication):
    """DRF authenticator : valide une signature HMAC + APIKey active.

    À ajouter à `authentication_classes` des vues exposées aux terminaux :

        class ScanView(APIView):
            authentication_classes = [HMACAPIKeyAuthentication, JWTAuthentication]
            permission_classes = [IsAuthenticatedOrAPIKey]

    Sur succès, `request.auth` contient l'APIKey. `request.user` reste anonyme
    (les passerelles ne sont pas des utilisateurs Django).
    """

    keyword = "HMAC"

    def authenticate(self, request) -> Optional[Tuple[None, object]]:
        meta = request.META
        # Ne s'active que si les 3 headers sont présents — sinon on laisse
        # le prochain authenticator (JWT) répondre.
        key_id = meta.get(HEADER_KEY_ID)
        ts = meta.get(HEADER_TS)
        sig = meta.get(HEADER_SIG)
        if not key_id or not ts or not sig:
            return None

        # 1. clock skew
        skew = int(getattr(settings, "KAYDAN_SHIELD", {}).get("API_KEY_CLOCK_SKEW_SEC", 60))
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            raise HMACSignatureError("Timestamp invalide.")
        now = int(time.time())
        if abs(now - ts_int) > skew:
            raise HMACSignatureError(
                f"Timestamp hors tolérance ({abs(now - ts_int)}s, max {skew}s).",
            )

        # 2. clé active
        from accounts.models import APIKey  # éviter import circulaire au boot
        try:
            api_key = APIKey.objects.select_related("tenant", "site").get(public_id=key_id)
        except APIKey.DoesNotExist:
            raise HMACSignatureError("Clé API inconnue.")
        if not api_key.is_active or api_key.revoked_at:
            raise HMACSignatureError("Clé API révoquée.")
        if api_key.expires_at and api_key.expires_at < timezone.now():
            raise HMACSignatureError("Clé API expirée.")

        # 3. signature
        expected = sign(
            api_key.secret_hash,
            ts,
            request.method,
            request.path,
            request.body,
        )
        if not hmac.compare_digest(expected, sig):
            logger.warning("HMAC invalide pour key_id=%s path=%s", key_id, request.path)
            raise HMACSignatureError("Signature HMAC invalide.")

        # 4. tracer last_used_at (best-effort, pas en transaction critique)
        try:
            APIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        except Exception:
            pass

        # request.user reste anonyme ; request.auth contient l'APIKey
        from django.contrib.auth.models import AnonymousUser
        return (AnonymousUser(), api_key)

    def authenticate_header(self, request):
        return self.keyword
