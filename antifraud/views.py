from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import BLEStillnessSignal, FraudAlert, FraudInvestigation, FraudRule, FraudScoring
from .serializers import (
    BLEStillnessSignalSerializer, FraudAlertSerializer, FraudInvestigationSerializer,
    FraudRuleSerializer, FraudScoringSerializer,
)


class FraudRuleViewSet(viewsets.ModelViewSet):
    queryset = FraudRule.objects.all(); serializer_class = FraudRuleSerializer
    filterset_fields = ("tenant", "severity", "is_active")
    search_fields = ("code", "name")


class FraudAlertViewSet(viewsets.ModelViewSet):
    queryset = FraudAlert.objects.select_related("rule", "site", "assigned_to").all()
    serializer_class = FraudAlertSerializer
    filterset_fields = ("tenant", "site", "status", "severity", "rule")

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.status = "acknowledged"
        alert.assigned_to = request.user
        alert.save(update_fields=["status", "assigned_to"])
        return Response(FraudAlertSerializer(alert).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        alert = self.get_object()
        alert.status = "confirmed"
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.resolution_comment = request.data.get("comment", "")
        alert.save()
        return Response(FraudAlertSerializer(alert).data)

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        alert = self.get_object()
        alert.status = "dismissed"
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.resolution_comment = request.data.get("comment", "")
        alert.save()
        return Response(FraudAlertSerializer(alert).data)

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        alert = self.get_object()
        alert.status = "escalated"
        alert.save(update_fields=["status"])
        return Response(FraudAlertSerializer(alert).data)


class FraudInvestigationViewSet(viewsets.ModelViewSet):
    queryset = FraudInvestigation.objects.prefetch_related("alerts").all()
    serializer_class = FraudInvestigationSerializer
    filterset_fields = ("tenant", "status")

    def get_queryset(self):
        # Investigation visible si au moins une alerte sur un site de la filiale.
        from accounts.scoping import get_user_company_ids
        qs = super().get_queryset()
        ids = get_user_company_ids(self.request.user)
        if ids is None:
            return qs
        if not ids:
            return qs.none()
        return qs.filter(alerts__site__company_id__in=ids).distinct()


class FraudScoringViewSet(viewsets.ReadOnlyModelViewSet):
    """Score de fraude par holder (employé/ouvrier/visiteur).

    Pas de FK directe vers Company — scoping fait via le holder lui-même
    quand pertinent. Actuellement on garde le filtrage tenant (filterset).
    """
    queryset = FraudScoring.objects.all(); serializer_class = FraudScoringSerializer
    filterset_fields = ("tenant", "holder_kind")


class BLEStillnessSignalViewSet(viewsets.ModelViewSet):
    queryset = BLEStillnessSignal.objects.select_related("helmet", "zone").all()
    serializer_class = BLEStillnessSignalSerializer
    filterset_fields = ("helmet", "zone")

    def get_queryset(self):
        # Signal BLE rattaché à une zone → site → company
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "zone__site__company")
