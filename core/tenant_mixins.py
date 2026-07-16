"""KAYDAN SHIELD — Mixins DRF multi-tenant réutilisables.

Objectif : éliminer les erreurs « tenant : ce champ est obligatoire »
partout où un ModelViewSet expose un modèle rattaché à un ``core.Tenant``.

Le front n'a jamais à connaître ni à envoyer le tenant : il est déduit
à la volée depuis ``request.user`` via ``devices.utils.resolve_tenant``.

Usage minimal côté ViewSet :

    from core.tenant_mixins import TenantScopedViewSetMixin

    class MyViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
        queryset = MyModel.objects.all()
        serializer_class = MySerializer

Le mixin fait deux choses :
    1. ``perform_create`` — injecte automatiquement ``tenant=<user tenant>``.
       Si le user n'a pas de tenant, retourne une 400 explicite.
    2. ``get_queryset`` — filtre implicitement sur le tenant de l'user
       (sauf super-user, qui voit tout).

Si le modèle n'a pas de champ ``tenant`` (ex : modèle global), il suffit
de définir ``tenant_field = None`` sur le viewset.
"""
from __future__ import annotations

from rest_framework.exceptions import ValidationError


class TenantScopedViewSetMixin:
    """Mixin ModelViewSet — auto tenant + auto-filtrage.

    Attributs surchargeables :
        tenant_field : str | None — nom du FK vers Tenant (défaut : "tenant").
                       Si None, le mixin n'agit pas (utile pour héritage
                       ponctuel où seul l'auto-filtre queryset est voulu).
    """

    tenant_field: str | None = "tenant"

    # ─── Écriture ───────────────────────────────────────────────
    def perform_create(self, serializer):
        if self.tenant_field is None:
            return super().perform_create(serializer)   # type: ignore

        tenant = self._resolve_current_tenant()
        if tenant is None:
            raise ValidationError({
                self.tenant_field: [
                    "Impossible de déterminer votre organisation. "
                    "Contactez un administrateur.",
                ],
            })
        serializer.save(**{self.tenant_field: tenant})

    # ─── Lecture ────────────────────────────────────────────────
    def get_queryset(self):
        qs = super().get_queryset()  # type: ignore
        if self.tenant_field is None:
            return qs

        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return qs.none()
        # Superuser voit tout — comportement historique
        if user.is_superuser or getattr(user, "is_staff", False):
            return qs

        tenant = self._resolve_current_tenant()
        if tenant is None:
            return qs.none()
        return qs.filter(**{self.tenant_field: tenant})

    # ─── Helper ─────────────────────────────────────────────────
    def _resolve_current_tenant(self):
        from devices.utils import resolve_tenant
        return resolve_tenant(self.request.user)
