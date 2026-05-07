from rest_framework import viewsets

from .models import AuditLog, ConformityRegister, DataExportRequest, LegalRetentionPolicy
from .serializers import (
    AuditLogSerializer, ConformityRegisterSerializer,
    DataExportRequestSerializer, LegalRetentionPolicySerializer,
)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all(); serializer_class = AuditLogSerializer
    filterset_fields = ("tenant", "user", "action", "target_model")
    search_fields = ("target_id",)


class DataExportRequestViewSet(viewsets.ModelViewSet):
    queryset = DataExportRequest.objects.all(); serializer_class = DataExportRequestSerializer
    filterset_fields = ("tenant", "status", "kind")


class LegalRetentionPolicyViewSet(viewsets.ModelViewSet):
    queryset = LegalRetentionPolicy.objects.all(); serializer_class = LegalRetentionPolicySerializer
    filterset_fields = ("tenant", "target_model", "is_active")


class ConformityRegisterViewSet(viewsets.ModelViewSet):
    queryset = ConformityRegister.objects.all(); serializer_class = ConformityRegisterSerializer
    filterset_fields = ("tenant", "site", "kind")
