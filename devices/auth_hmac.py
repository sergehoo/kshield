"""KAYDAN SHIELD — vérification HMAC + anti-rejeu pour endpoints agent.

Le serveur exige que les endpoints agent HTTP (fallback) soient signés :

    Headers :
        Authorization         : Bearer <api_token>
        X-Kshield-Timestamp   : <epoch>
        X-Kshield-Signature   : <hex hmac_sha256(secret, f"{ts}.{body}")>

Comportement :
  * Refuse si timestamp diffère de plus de 5 min de now (anti-rejeu)
  * Refuse si signature invalide
  * Si l'agent n'a pas de ``hmac_secret`` configuré → auth token seul (mode legacy)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)

CLOCK_SKEW_SECONDS = 300


class AgentHmacAuthentication(authentication.BaseAuthentication):
    """Authentification agent = Bearer token + signature HMAC optionnelle.

    Attaché à la request : ``request.agent`` (LocalAgent instance).
    """

    def authenticate(self, request):
        from .models import LocalAgent

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        try:
            agent = LocalAgent.objects.get(api_token=token)
        except LocalAgent.DoesNotExist:
            raise exceptions.AuthenticationFailed("Token agent invalide.")

        # Si l'agent a un secret HMAC configuré → vérification signature obligatoire
        if agent.hmac_secret:
            ts = request.META.get("HTTP_X_KSHIELD_TIMESTAMP", "")
            sig = request.META.get("HTTP_X_KSHIELD_SIGNATURE", "")
            if not (ts and sig):
                raise exceptions.AuthenticationFailed(
                    "Headers HMAC manquants (X-Kshield-Timestamp + X-Kshield-Signature).",
                )
            try:
                ts_int = int(ts)
            except ValueError:
                raise exceptions.AuthenticationFailed("Timestamp invalide.")
            if abs(time.time() - ts_int) > CLOCK_SKEW_SECONDS:
                raise exceptions.AuthenticationFailed(
                    "Timestamp trop ancien (anti-rejeu).",
                )
            body = request.body or b""
            expected = hmac.new(
                agent.hmac_secret.encode(),
                f"{ts}.{body.decode('utf-8', errors='replace')}".encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise exceptions.AuthenticationFailed("Signature HMAC invalide.")

        # Attache l'agent à la request pour usage downstream
        request.agent = agent  # type: ignore[attr-defined]
        return (agent, None)   # user, auth (DRF signature)
