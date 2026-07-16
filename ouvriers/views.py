from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from core.tenancy import resolve_request_tenant
from core.tenant_mixins import TenantScopedViewSetMixin

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification
from .serializers import (
    CrewSerializer, SubcontractorSerializer, TradeSerializer, WorkerAssignmentSerializer,
    WorkerCertificationSerializer, WorkerSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Ouvriers"], summary="Référentiel des métiers"),
    create=extend_schema(tags=["Ouvriers"]),
    retrieve=extend_schema(tags=["Ouvriers"]),
    update=extend_schema(tags=["Ouvriers"]),
    partial_update=extend_schema(tags=["Ouvriers"]),
    destroy=extend_schema(tags=["Ouvriers"]),
)
class TradeViewSet(viewsets.ModelViewSet):
    queryset = Trade.objects.all(); serializer_class = TradeSerializer; search_fields = ("name", "code")


@extend_schema_view(
    list=extend_schema(tags=["Ouvriers"], summary="Sous-traitants chantiers"),
    create=extend_schema(tags=["Ouvriers"]),
    retrieve=extend_schema(tags=["Ouvriers"]),
    update=extend_schema(tags=["Ouvriers"]),
    partial_update=extend_schema(tags=["Ouvriers"]),
    destroy=extend_schema(tags=["Ouvriers"]),
)
class SubcontractorViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Subcontractor.objects.all(); serializer_class = SubcontractorSerializer
    search_fields = ("name", "code"); filterset_fields = ("tenant", "is_active")


@extend_schema_view(
    list=extend_schema(tags=["Ouvriers"], summary="Liste des ouvriers chantier",
        description="Ouvriers BTP — couplage badge UHF + casque connecté."),
    create=extend_schema(tags=["Ouvriers"], summary="Créer un ouvrier"),
    retrieve=extend_schema(tags=["Ouvriers"], summary="Détail ouvrier"),
    update=extend_schema(tags=["Ouvriers"]),
    partial_update=extend_schema(tags=["Ouvriers"]),
    destroy=extend_schema(tags=["Ouvriers"]),
)
class WorkerViewSet(viewsets.ModelViewSet):
    """Personnel chantier (direct ou sous-traitant) avec UHF + casque."""
    queryset = Worker.objects.select_related("trade", "subcontractor").all()
    serializer_class = WorkerSerializer
    search_fields = ("matricule", "first_name", "last_name", "phone", "id_document_number")
    filterset_fields = ("tenant", "trade", "subcontractor", "status")

    def perform_create(self, serializer):
        tenant = resolve_request_tenant(self.request)
        serializer.save(
            tenant=tenant,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_queryset(self):
        # Worker n'a pas de FK direct vers Company. On le rattache via
        # assignments.site.company OU crews.site.company (un worker mobile
        # sur plusieurs sites est visible si AU MOINS UN site est dans la filiale).
        from accounts.scoping import get_user_company_ids
        qs = super().get_queryset()
        ids = get_user_company_ids(self.request.user)
        if ids is None:
            return qs  # accès global
        if not ids:
            return qs.none()
        return qs.filter(
            models.Q(assignments__site__company_id__in=ids)
            | models.Q(crews__site__company_id__in=ids)
        ).distinct()


class WorkerCertificationViewSet(viewsets.ModelViewSet):
    queryset = WorkerCertification.objects.select_related("worker").all()
    serializer_class = WorkerCertificationSerializer
    filterset_fields = ("worker", "code")

    def get_queryset(self):
        # Certification visible si l'ouvrier est rattaché à un site de la filiale.
        from accounts.scoping import get_user_company_ids
        qs = super().get_queryset()
        ids = get_user_company_ids(self.request.user)
        if ids is None:
            return qs
        if not ids:
            return qs.none()
        return qs.filter(
            models.Q(worker__assignments__site__company_id__in=ids)
            | models.Q(worker__crews__site__company_id__in=ids)
        ).distinct()


class CrewViewSet(viewsets.ModelViewSet):
    queryset = Crew.objects.select_related("site", "foreman").prefetch_related("members").all()
    serializer_class = CrewSerializer
    filterset_fields = ("site", "is_active")

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class WorkerAssignmentViewSet(viewsets.ModelViewSet):
    queryset = WorkerAssignment.objects.select_related("worker", "site", "crew").all()
    serializer_class = WorkerAssignmentSerializer
    filterset_fields = ("worker", "site", "crew", "is_active")

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")
