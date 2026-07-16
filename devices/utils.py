"""KAYDAN SHIELD — helpers partagés pour l'app devices."""
from __future__ import annotations


def resolve_tenant(user):
    """Résout un tenant utilisable pour un user, même sans relation directe.

    Ordre :
      1. ``user.tenant`` (relation directe)
      2. ``user.company.tenant`` (utilisateur rattaché à une filiale)
      3. Superuser → premier tenant actif (le SU est global)
      4. ``core.services.get_kaydan_tenant()`` (fallback historique)
      5. Premier tenant actif de la base (dernier recours si un seul existe)
      6. None (aucun tenant du tout — DB vide)
    """
    t = getattr(user, "tenant", None)
    if t is not None:
        return t
    company = getattr(user, "company", None)
    if company is not None and company.tenant_id:
        return company.tenant
    try:
        from core.models import Tenant
        active_qs = Tenant.objects.filter(is_active=True)
    except Exception:
        active_qs = None

    if getattr(user, "is_superuser", False) and active_qs is not None:
        first = active_qs.first()
        if first is not None:
            return first

    try:
        from core.services import get_kaydan_tenant
        t = get_kaydan_tenant()
        if t is not None:
            return t
    except Exception:
        pass

    # Dernier recours : s'il n'existe qu'un seul tenant, l'utiliser
    if active_qs is not None:
        first = active_qs.first()
        if first is not None:
            return first
    return None
