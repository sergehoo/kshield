"""KAYDAN SHIELD — Services métier transverses du module core.

Centralise la résolution du tenant singleton KAYDAN GROUPE. KAYDAN est
l'unique tenant de la plateforme — ce qui change, ce sont les filiales
(Companies) rattachées à ce tenant.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

KAYDAN_TENANT_CODE = "kaydan"
KAYDAN_TENANT_NAME = "KAYDAN GROUPE"


class KaydanTenantService:
    """Singleton thread-safe pour résoudre le tenant KAYDAN.

    - `get()` retourne le tenant unique (le crée si absent à la 1ère demande).
    - `reset_cache()` vide le cache (utile en tests entre transactions).
    """

    _cached: Optional[object] = None

    @classmethod
    def get(cls):
        """Retourne le tenant KAYDAN, le crée idempotemment si absent."""
        if cls._cached is not None:
            return cls._cached

        from .models import Tenant
        tenant, created = Tenant.objects.get_or_create(
            code=KAYDAN_TENANT_CODE,
            defaults={
                "name": KAYDAN_TENANT_NAME,
                "timezone": "Africa/Abidjan",
                "currency": "XOF",
                "is_active": True,
            },
        )
        if created:
            log.info("Tenant KAYDAN créé automatiquement (code=%s)",
                     KAYDAN_TENANT_CODE)
        cls._cached = tenant
        return tenant

    @classmethod
    def reset_cache(cls):
        cls._cached = None


def get_kaydan_tenant():
    """Raccourci fonctionnel — équivalent de `KaydanTenantService.get()`.

    ⚠️  Legacy : utilise ``get_current_tenant()`` à la place pour le code
    multi-tenant. ``get_kaydan_tenant()`` reste pour les usages où aucun
    request n'est disponible (Celery tasks, management commands).
    """
    return KaydanTenantService.get()


# ─────────────────────────────────────────────────────────────────────────────
# Tenant courant (multi-tenant aware)
# ─────────────────────────────────────────────────────────────────────────────
import threading

_local = threading.local()


def set_current_tenant(tenant):
    """Set le tenant courant pour le thread (appelé par TenantContextMiddleware)."""
    _local.tenant = tenant


def get_current_tenant():
    """Renvoie le tenant scopé au request en cours, fallback sur Kaydan.

    Usage prioritaire dans tout le code applicatif :
        from core.services import get_current_tenant
        tenant = get_current_tenant()

    Dans les Celery tasks : passer explicitement ``tenant_id`` en argument
    et faire ``Tenant.objects.get(pk=tenant_id)``, car le thread-local
    n'est pas peuplé hors d'un cycle requête HTTP.
    """
    t = getattr(_local, "tenant", None)
    if t is not None:
        return t
    return get_kaydan_tenant()


def clear_current_tenant():
    """Réinitialise le tenant (fin de request)."""
    _local.tenant = None
