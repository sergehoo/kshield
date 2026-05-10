from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

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
class SubcontractorViewSet(viewsets.ModelViewSet):
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


class WorkerCertificationViewSet(viewsets.ModelViewSet):
    queryset = WorkerCertification.objects.select_related("worker").all()
    serializer_class = WorkerCertificationSerializer
    filterset_fields = ("worker", "code")


class CrewViewSet(viewsets.ModelViewSet):
    queryset = Crew.objects.select_related("site", "foreman").prefetch_related("members").all()
    serializer_class = CrewSerializer
    filterset_fields = ("site", "is_active")


class WorkerAssignmentViewSet(viewsets.ModelViewSet):
    queryset = WorkerAssignment.objects.select_related("worker", "site", "crew").all()
    serializer_class = WorkerAssignmentSerializer
    filterset_fields = ("worker", "site", "crew", "is_active")
