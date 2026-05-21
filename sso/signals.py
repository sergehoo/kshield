"""Signals SSO :
- Désactive l'user Keycloak quand on désactive un User local
- Invalide les caches RBAC + offline quand le user est modifié
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def _on_user_saved(sender, instance, created, **kwargs):
    if created:
        return
    # Si le user a été désactivé, on essaie de le déconnecter de Keycloak
    if not instance.is_active:
        try:
            from sso.adapters import (disable_keycloak_user,
                                        force_logout_keycloak_user)
            from sso.models import OfflineUserCredentialCache
            ident = getattr(instance, "sso_identity", None)
            if ident and getattr(settings, "SSO_ENABLED", False):
                force_logout_keycloak_user(ident.subject)
                disable_keycloak_user(ident.subject)
            # Invalide tous les caches offline
            OfflineUserCredentialCache.objects.filter(
                user=instance, is_active=True,
            ).update(is_active=False)
        except Exception:
            logger.debug("sso signal disable failed", exc_info=True)

    # Cache RBAC
    try:
        from accounts.rbac import invalidate_user_perms
        invalidate_user_perms(instance.pk)
    except Exception:
        logger.debug("sso signal rbac invalidate failed", exc_info=True)
