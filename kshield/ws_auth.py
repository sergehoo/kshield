"""KAYDAN SHIELD — Channels middleware d'auth par JWT en query string.

Le front connecte les WebSockets via `wss://.../ws/…/?token=<JWT>` — parce
que les headers custom ne sont pas supportés par l'API native WebSocket
navigateur. Ce middleware :

    1. lit le paramètre `token` de la query string du handshake ;
    2. valide le JWT via rest_framework_simplejwt.tokens.AccessToken ;
    3. charge l'utilisateur correspondant en base ;
    4. injecte `scope["user"]` — comme AuthMiddlewareStack le ferait
       pour une session Django.

Si le token est absent, invalide ou expiré, on laisse `AnonymousUser`
en place (le consumer décide de fermer ou non).

Monté dans kshield/asgi.py autour du URLRouter.
"""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_token(raw_token: str):
    """Résout un utilisateur à partir d'un JWT SimpleJWT."""
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError
    except Exception:                                     # pragma: no cover
        return AnonymousUser()
    User = get_user_model()
    try:
        token = AccessToken(raw_token)
        user_id = token.get("user_id")
        if not user_id:
            return AnonymousUser()
        return User.objects.filter(pk=user_id, is_active=True).first() \
                or AnonymousUser()
    except (TokenError, Exception):
        return AnonymousUser()


class JWTAuthMiddleware:
    """Populate scope['user'] depuis ?token=<JWT> pour les handshakes WS."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        qs = scope.get("query_string", b"") or b""
        try:
            params = parse_qs(qs.decode("utf-8"))
        except Exception:
            params = {}
        token = None
        vals = params.get("token") or params.get("jwt") or []
        if vals:
            token = vals[0]

        if token and (not scope.get("user")
                      or not getattr(scope["user"], "is_authenticated", False)):
            scope["user"] = await _get_user_from_token(token)
        elif "user" not in scope:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Petit helper utilisable comme AuthMiddlewareStack."""
    from channels.auth import AuthMiddlewareStack
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
