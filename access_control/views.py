from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AccessDecision, AccessEvent, AccessRule, DoorCommand, QRCodeToken
from .serializers import (
    AccessDecisionSerializer, AccessEventSerializer, AccessRuleSerializer,
    DoorCommandSerializer, QRCodeTokenSerializer, ScanSerializer,
)
from .services import AccessGatewayService


class ScanView(APIView):
    """POST /api/v1/access/scan — appelée par chaque terminal IoT."""

    def post(self, request):
        serializer = ScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = AccessGatewayService.process_scan(
            serializer.validated_data, operator=request.user if request.user.is_authenticated else None,
        )
        return Response(AccessEventSerializer(event).data, status=status.HTTP_201_CREATED)


class AccessEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AccessEvent.objects.select_related(
        "site", "zone", "checkpoint", "device", "operator",
    ).all()
    serializer_class = AccessEventSerializer
    filterset_fields = ("tenant", "site", "device", "decision", "method", "holder_kind", "direction")
    search_fields = ("badge_uid", "helmet_uid", "denial_reason")


class AccessRuleViewSet(viewsets.ModelViewSet):
    queryset = AccessRule.objects.all(); serializer_class = AccessRuleSerializer
    filterset_fields = ("tenant", "site", "type", "severity", "is_active")


class AccessDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AccessDecision.objects.all(); serializer_class = AccessDecisionSerializer


class DoorCommandViewSet(viewsets.ModelViewSet):
    queryset = DoorCommand.objects.all(); serializer_class = DoorCommandSerializer
    filterset_fields = ("checkpoint", "command", "status")


class QRCodeTokenViewSet(viewsets.ModelViewSet):
    queryset = QRCodeToken.objects.all(); serializer_class = QRCodeTokenSerializer
    filterset_fields = ("visit_request", "single_use")
