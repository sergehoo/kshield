from drf_spectacular.utils import (OpenApiExample, OpenApiResponse,
                                     extend_schema, extend_schema_view)
from django.contrib.contenttypes.prefetch import GenericPrefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.hmac_auth import HMACAPIKeyAuthentication
from accounts.permissions import IsAuthenticatedOrAPIKey
from employees.models import Employee
from ouvriers.models import Worker
from visitors.models import Visitor

from .models import AccessDecision, AccessEvent, AccessRule, DoorCommand, QRCodeToken
from .serializers import (
    AccessDecisionSerializer, AccessEventDetailSerializer, AccessEventSerializer,
    AccessRuleSerializer, DoorCommandSerializer, QRCodeTokenSerializer, ScanSerializer,
)
from .services import AccessGatewayService


@extend_schema(
    tags=["Acces"],
    summary="Scan d'un badge ou casque (terminal IoT)",
    description=(
        "Endpoint principal appelé par chaque terminal NFC/UHF/QR. "
        "Authentification : signature HMAC via X-KShield-Key-Id / X-KShield-Timestamp / "
        "X-KShield-Signature, OU token JWT pour les tests admin."
    ),
    request=ScanSerializer,
    responses={201: AccessEventSerializer},
    examples=[
        OpenApiExample(
            "NFC employé",
            value={
                "device_serial": "DEV-NFC-001",
                "badge_uid": "EMP-04F7-3A21",
                "method": "nfc",
                "direction": "in",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Worker UHF + helmet",
            value={
                "device_serial": "DEV-UHF-001",
                "badge_uid": "OV-A12B-91FF",
                "helmet_uid": "HLM-22C8",
                "method": "uhf",
                "direction": "in",
                "latitude": 5.345, "longitude": -4.025,
            },
            request_only=True,
        ),
    ],
)
class ScanView(APIView):
    """POST /api/v1/access/scan — appelée par chaque terminal IoT.

    Auth : HMAC (X-KShield-Key-Id/Timestamp/Signature) OU JWT (back-office).
    """

    authentication_classes = [HMACAPIKeyAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticatedOrAPIKey]

    def post(self, request):
        serializer = ScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = AccessGatewayService.process_scan(
            serializer.validated_data, operator=request.user if request.user.is_authenticated else None,
        )
        return Response(
            AccessEventSerializer(event, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Acces"],
        summary="Historique des événements d'accès",
        description="Lecture seule — historique des scans (granted/denied/review). "
                    "Filtres : tenant, site, device, decision, method, holder_kind, direction.",
    ),
    retrieve=extend_schema(tags=["Acces"], summary="Détail d'un événement"),
)
class AccessEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AccessEvent.objects.select_related(
        "site__company", "zone", "checkpoint", "device__model", "operator",
        "holder_content_type",
    ).prefetch_related(
        GenericPrefetch(
            "holder",
            [
                Employee.objects.select_related("position", "department"),
                Worker.objects.select_related("trade", "subcontractor"),
                Visitor.objects.all(),
            ],
        ),
    ).all()
    serializer_class = AccessEventSerializer
    filterset_fields = ("tenant", "site", "device", "decision", "method", "holder_kind", "direction")
    search_fields = ("badge_uid", "helmet_uid", "denial_reason")

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        queryset = scope_queryset_by_company(
            super().get_queryset(), self.request.user, "site__company",
        )
        if self.action == "retrieve":
            return queryset.select_related("decision_trace").prefetch_related("door_commands")
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AccessEventDetailSerializer
        return AccessEventSerializer


class AccessRuleViewSet(viewsets.ModelViewSet):
    queryset = AccessRule.objects.all(); serializer_class = AccessRuleSerializer
    filterset_fields = ("tenant", "site", "type", "severity", "is_active")

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class AccessDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AccessDecision.objects.all(); serializer_class = AccessDecisionSerializer


class DoorCommandViewSet(viewsets.ModelViewSet):
    queryset = DoorCommand.objects.all(); serializer_class = DoorCommandSerializer
    filterset_fields = ("checkpoint", "command", "status")


class QRCodeTokenViewSet(viewsets.ModelViewSet):
    queryset = QRCodeToken.objects.all(); serializer_class = QRCodeTokenSerializer
    filterset_fields = ("visit_request", "single_use")
