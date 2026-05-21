"""KAYDAN SHIELD — Backend OIDC custom basé sur mozilla-django-oidc.

Étend `OIDCAuthenticationBackend` pour :
- créer ou matcher l'utilisateur via SSOIdentity (subject Keycloak)
- conserver les permissions métier locales (RoleAssignment KAYDAN)
- synchroniser les rôles globaux (SSORoleMapping)
- bloquer le login si l'user est désactivé localement
- auditer chaque tentative dans SSOLoginAudit
"""
from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from mozilla_django_oidc.auth import OIDCAuthenticationBackend
except ImportError:
    # Permet à Django de booter même si mozilla-django-oidc n'est pas
    # encore installé — tant que SSO_ENABLED=False.
    class OIDCAuthenticationBackend:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "Installez mozilla-django-oidc pour activer le SSO Keycloak."
            )


class KaydanOIDCBackend(OIDCAuthenticationBackend):
    """Backend OIDC qui utilise le système SSOIdentity de KAYDAN."""

    def filter_users_by_claims(self, claims):
        """Match user via subject Keycloak puis fallback email."""
        from sso.models import SSOIdentity
        sub = claims.get("sub")
        if sub:
            ident = SSOIdentity.objects.filter(subject=sub).select_related("user")
            if ident.exists():
                return [ident.first().user]
        email = (claims.get("email") or "").lower()
        if email:
            return list(self.UserModel.objects.filter(email__iexact=email))
        return []

    def create_user(self, claims):
        """Délègue au service centralisé."""
        from sso.services import get_or_create_user_from_claims
        user, _, _ = get_or_create_user_from_claims(claims)
        return user

    def update_user(self, user, claims):
        """Met à jour les métadonnées au login (rôles + last_login_ip)."""
        from sso.services import get_or_create_user_from_claims
        user, _, _ = get_or_create_user_from_claims(claims)
        return user

    def get_userinfo(self, access_token, id_token, payload):
        """Audit sur chaque récupération de userinfo."""
        try:
            return super().get_userinfo(access_token, id_token, payload)
        except Exception:
            from sso.models import SSOLoginAudit
            SSOLoginAudit.objects.create(
                kind="token_invalid",
                success=False,
                reason="get_userinfo a échoué",
            )
            raise

    def authenticate(self, request, **kwargs):
        user = super().authenticate(request, **kwargs)
        # Audit log si on a un user et un request
        try:
            from sso.models import SSOLoginAudit
            ip = request.META.get("REMOTE_ADDR") if request else None
            ua = (request.META.get("HTTP_USER_AGENT", "") if request else "")[:500]
            if user is not None:
                SSOLoginAudit.objects.create(
                    user=user, email=user.email,
                    subject=getattr(getattr(user, "sso_identity", None), "subject", ""),
                    kind="login_success", success=True,
                    ip=ip, user_agent=ua,
                )
                # Met à jour SSOIdentity.last_login_ip
                if hasattr(user, "sso_identity"):
                    user.sso_identity.last_login_ip = ip
                    user.sso_identity.last_synced_at = timezone.now()
                    user.sso_identity.save(update_fields=["last_login_ip", "last_synced_at"])
            else:
                SSOLoginAudit.objects.create(
                    kind="login_failure", success=False,
                    reason="Backend a refusé le user",
                    ip=ip, user_agent=ua,
                )
        except Exception:
            logger.exception("Audit SSO échoué (non bloquant)")
        return user
