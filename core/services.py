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
    """Raccourci fonctionnel — équivalent de `KaydanTenantService.get()`."""
    return KaydanTenantService.get()
