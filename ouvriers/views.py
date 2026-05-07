from rest_framework import viewsets

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification
from .serializers import (
    CrewSerializer, SubcontractorSerializer, TradeSerializer, WorkerAssignmentSerializer,
    WorkerCertificationSerializer, WorkerSerializer,
)


class TradeViewSet(viewsets.ModelViewSet):
    queryset = Trade.objects.all(); serializer_class = TradeSerializer; search_fields = ("name", "code")


class SubcontractorViewSet(viewsets.ModelViewSet):
    queryset = Subcontractor.objects.all(); serializer_class = SubcontractorSerializer
    search_fields = ("name", "code"); filterset_fields = ("tenant", "is_active")


class WorkerViewSet(viewsets.ModelViewSet):
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
