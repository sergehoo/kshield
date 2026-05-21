"""Authentification DRF par token Keycloak (Bearer)."""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions, permissions

logger = logging.getLogger(__name__)
User = get_user_model()


class KeycloakBearerAuthentication(authentication.BaseAuthentication):
    """Valide un access_token JWT Keycloak côté DRF.

    Header : `Authorization: Bearer <jwt>`
    Vérifie : signature via JWKS, expiration, audience, issuer.
    Sur succès, attache le User local correspondant via SSOIdentity.subject.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith(self.keyword + " "):
            return None
        token = auth[len(self.keyword) + 1:].strip()
        if not token:
            return None
        try:
            from sso.utils import decode_jwt
            claims = decode_jwt(token)
        except Exception as exc:
            logger.debug("JWT invalide : %s", exc, exc_info=True)
            try:
                from sso.models import SSOLoginAudit
                SSOLoginAudit.objects.create(
                    kind="token_invalid", success=False,
                    reason=str(exc)[:300],
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except Exception:
                logger.warning("SSOLoginAudit token_invalid non persisté", exc_info=True)
            raise exceptions.AuthenticationFailed("Token invalide ou expiré.")

        sub = claims.get("sub")
        if not sub:
            raise exceptions.AuthenticationFailed("Claim 'sub' manquant.")

        # Provisioning à la volée si pas encore connu
        from sso.services import get_or_create_user_from_claims
        try:
            user, _, _ = get_or_create_user_from_claims(claims)
        except (PermissionError, ValueError) as exc:
            raise exceptions.AuthenticationFailed(str(exc))

        return (user, token)

    def authenticate_header(self, request):
        return self.keyword


class IsKaydanUser(permissions.BasePermission):
    """Permission DRF : autorise tout user authentifié avec un User local."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
