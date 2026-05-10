"""KAYDAN SHIELD — Helpers RBAC.

Modèle :
    User → RoleAssignment(role, site=None) → Role → RolePermission(code)

`code` est une string `module.action` (ex. "employees.view", "badges.issue").
Un superuser passe toutes les checks.

Usage dans les vues :
    class EmployeesView(KshieldPermissionMixin, BaseAdminView):
        permission_required = "employees.view"
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from django.contrib.auth.mixins import AccessMixin
from django.core.cache import cache


def user_permissions(user) -> set[str]:
    """Retourne l'ensemble des codes permission du user (cache 60s)."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {"*"}
    cache_key = f"rbac:perms:{user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from accounts.models import RolePermission
        perms = set(RolePermission.objects.filter(
            role__assignments__user=user,
        ).values_list("code", flat=True).distinct())
    except Exception:
        perms = set()
    cache.set(cache_key, perms, 60)
    return perms


def user_has_permission(user, code: str) -> bool:
    """True si le user a la permission `code` (ou est superuser/staff fallback)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perms = user_permissions(user)
    if "*" in perms:
        return True
    if code in perms:
        return True
    # Wildcard module : "employees.*" couvre "employees.view" etc.
    module = code.split(".")[0] + ".*"
    if module in perms:
        return True
    # Fallback : staff a tout en lecture (les boutons modify/delete restent contrôlés)
    if user.is_staff and code.endswith(".view"):
        return True
    return False


def user_has_any(user, codes: Iterable[str]) -> bool:
    return any(user_has_permission(user, c) for c in codes)


def invalidate_user_perms(user_id: int):
    cache.delete(f"rbac:perms:{user_id}")


# ─── Catalogue centralisé des permissions exposées dans la UI ───────────
PERMISSION_CATALOG = [
    ("Pilotage", [
        ("dashboard.view", "Voir le tableau de bord"),
        ("realtime.view", "Voir le flux temps réel"),
        ("realtime.export", "Exporter le flux Excel"),
        ("map.view", "Voir la cartographie"),
    ]),
    ("Identités", [
        ("employees.view", "Voir les employés"),
        ("employees.manage", "Créer / modifier / supprimer un employé"),
        ("workers.view", "Voir les ouvriers"),
        ("workers.manage", "Gérer ouvriers, certifications, équipes, affectations"),
        ("visitors.view", "Voir les visiteurs"),
        ("visitors.manage", "Gérer demandes, invitations, watchlist"),
        ("visitors.checkin", "Effectuer les check-in / check-out"),
    ]),
    ("Terrain", [
        ("sites.view", "Voir sites & zones"),
        ("sites.manage", "Gérer sites, zones, checkpoints"),
        ("devices.view", "Voir équipements & heartbeats"),
        ("devices.manage", "Gérer équipements, OTA, maintenance"),
        ("badges.view", "Voir badges & casques"),
        ("badges.issue", "Émettre / révoquer / suspendre badges"),
        ("gateways.manage", "Gérer les passerelles edge"),
    ]),
    ("Sécurité", [
        ("attendance.view", "Voir le pointage"),
        ("attendance.correct", "Corriger un pointage"),
        ("access.view", "Voir les règles d'accès"),
        ("access.manage", "Créer / modifier les règles d'accès"),
        ("antifraud.view", "Voir les alertes anti-fraude"),
        ("antifraud.acknowledge_alert", "Acquitter / faux-positif / escalader"),
        ("antifraud.investigate", "Lancer / piloter une enquête"),
        ("audit.view", "Consulter le journal d'audit"),
        ("audit.export", "Générer un export RGPD"),
    ]),
    ("Communication & Reporting", [
        ("notifications.view", "Voir les notifications"),
        ("notifications.send", "Envoyer une notification"),
        ("reports.view", "Voir les rapports & KPI"),
        ("reports.run", "Exécuter un rapport"),
    ]),
    ("Système", [
        ("accounts.view", "Voir les utilisateurs"),
        ("accounts.manage", "Créer / modifier / désactiver un user"),
        ("roles.manage", "Gérer rôles & permissions"),
        ("apikeys.manage", "Créer / révoquer les clés API IoT"),
        ("companies.view", "Voir les filiales"),
        ("companies.manage", "Gérer les filiales"),
        ("settings.manage", "Modifier paramètres KAYDAN"),
    ]),
]


def all_known_codes() -> list[str]:
    out = []
    for _, items in PERMISSION_CATALOG:
        for code, _ in items:
            out.append(code)
    return out


# ─── Mixin DRF + Django CBV ─────────────────────────────────────────────
class KshieldPermissionMixin(AccessMixin):
    """Mixin pour CBV : vérifie permission_required avant le dispatch.

    `permission_required` peut être une string ou une liste.
    None = pas de check (visible aux authentifiés).
    """
    permission_required: str | list[str] | None = None
    raise_exception = False  # → redirect vers login plutôt que 403

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        codes = self.permission_required
        if codes is None:
            return super().dispatch(request, *args, **kwargs)
        if isinstance(codes, str):
            codes = [codes]
        if not user_has_any(request.user, codes):
            from django.contrib import messages as dj_messages
            dj_messages.error(request,
                "Permission refusée — contactez votre administrateur.")
            from django.shortcuts import redirect
            return redirect("admin-dashboard")
        return super().dispatch(request, *args, **kwargs)
