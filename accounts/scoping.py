"""KAYDAN SHIELD — Scoping multi-filiale (RBAC par Company).

Architecture :

    User ─┬─ company (FK Company, "filiale principale")
          ├─ extra_companies (M2M, accès secondaires si besoin)
          └─ permissions :
              ├─ "*"                  → superadmin, accès global
              ├─ "companies.view_all" → accès global explicite
              └─ sinon                → restreint à user.company + extras

Chaque ViewSet / view back-office qui veut être scopé appelle :

    scope_queryset_by_company(qs, request.user, "company")

ou pour les tables qui passent par site :

    scope_queryset_by_company(qs, request.user, "site__company")

Les modèles sans rapport à une filiale (TenantSettings, FeatureFlag) ne
sont jamais scopés.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Codes permission ajoutés au catalog (cf. accounts/rbac.py PERMISSION_CATALOG)
PERM_VIEW_ALL_COMPANIES = "companies.view_all"


# ---------------------------------------------------------------------------
# Calcul des filiales accessibles
# ---------------------------------------------------------------------------
def get_user_company_ids(user) -> Optional[list[int]]:
    """Retourne les IDs Company accessibles au user, ou None si accès global.

    Returns:
        None            → accès global (superuser ou permission companies.view_all)
        [int, int, ...] → liste des companies (peut être vide = aucun accès)
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []

    if getattr(user, "is_superuser", False):
        return None

    # Permission "voir toutes les filiales" → accès global
    try:
        from accounts.rbac import user_permissions
        perms = user_permissions(user)
        if "*" in perms or PERM_VIEW_ALL_COMPANIES in perms:
            return None
    except Exception:
        logger.debug("user_permissions a échoué, fallback restrictif", exc_info=True)

    ids = []
    # Filiale principale
    cid = getattr(user, "company_id", None)
    if cid:
        ids.append(cid)
    # Filiales secondaires (M2M optionnel — si le champ n'existe pas, on skip)
    extras_mgr = getattr(user, "extra_companies", None)
    if extras_mgr is not None:
        try:
            ids.extend(extras_mgr.values_list("pk", flat=True))
        except Exception:
            pass
    # Dédup tout en gardant l'ordre
    seen = set()
    out = []
    for v in ids:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def has_access_to_company(user, company_id: int) -> bool:
    """Vérifie l'accès à une filiale précise."""
    allowed = get_user_company_ids(user)
    if allowed is None:
        return True
    return int(company_id) in allowed


# ---------------------------------------------------------------------------
# Filtre queryset
# ---------------------------------------------------------------------------
def scope_queryset_by_company(qs, user, company_field: str = "company"):
    """Restreint un queryset selon les filiales du user.

    Args:
        qs: QuerySet à filtrer.
        user: l'utilisateur courant (request.user).
        company_field: nom du champ FK vers Company (ex. "company",
            "site__company", "department__company").

    Si user a accès global → qs inchangé.
    Si user a une liste de filiales → qs filtré sur ces filiales.
    Si user n'a aucun accès → qs.none().
    """
    allowed = get_user_company_ids(user)
    if allowed is None:
        return qs
    if not allowed:
        return qs.none()
    return qs.filter(**{f"{company_field}__in": allowed})


# ---------------------------------------------------------------------------
# Mixin DRF (à appliquer sur ViewSets sensibles)
# ---------------------------------------------------------------------------
class CompanyScopedMixin:
    """Mixin DRF qui ajoute le scoping company automatique.

    Usage :
        class EmployeeViewSet(CompanyScopedMixin, ModelViewSet):
            queryset = Employee.objects.all()
            company_lookup = "company"   # défaut

    Pour les modèles indirects :
        class PunchViewSet(CompanyScopedMixin, ModelViewSet):
            company_lookup = "site__company"
    """
    company_lookup: str = "company"

    def get_queryset(self):
        qs = super().get_queryset()
        return scope_queryset_by_company(qs, self.request.user, self.company_lookup)
