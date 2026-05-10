from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    VisitLog, VisitPurpose, VisitRequest, Visitor, VisitorIDDocument,
    VisitorInvitation, VisitorPass, Watchlist,
)
from .serializers import (
    VisitLogSerializer, VisitPurposeSerializer, VisitRequestSerializer, VisitorIDDocumentSerializer,
    VisitorInvitationSerializer, VisitorPassSerializer, VisitorSerializer, WalkInCheckInSerializer,
    WatchlistSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Visiteurs"], summary="Catalogue des motifs de visite"),
    create=extend_schema(tags=["Visiteurs"]),
    retrieve=extend_schema(tags=["Visiteurs"]),
    update=extend_schema(tags=["Visiteurs"]),
    partial_update=extend_schema(tags=["Visiteurs"]),
    destroy=extend_schema(tags=["Visiteurs"]),
)
class VisitPurposeViewSet(viewsets.ModelViewSet):
    queryset = VisitPurpose.objects.all(); serializer_class = VisitPurposeSerializer
    filterset_fields = ("is_active",)


@extend_schema_view(
    list=extend_schema(tags=["Visiteurs"], summary="Liste des visiteurs",
        description="Filtre par tenant et type de pièce d'identité. "
                    "Recherche sur nom/numéro CNI/email/phone."),
    create=extend_schema(tags=["Visiteurs"], summary="Créer un visiteur"),
    retrieve=extend_schema(tags=["Visiteurs"]),
    update=extend_schema(tags=["Visiteurs"]),
    partial_update=extend_schema(tags=["Visiteurs"]),
    destroy=extend_schema(tags=["Visiteurs"]),
)
class VisitorViewSet(viewsets.ModelViewSet):
    """OCR pièce d'identité + QR self-service / walk-in à l'accueil."""
    queryset = Visitor.objects.all(); serializer_class = VisitorSerializer
    search_fields = ("first_name", "last_name", "id_number", "phone", "email")
    filterset_fields = ("tenant", "id_type")


class VisitorIDDocumentViewSet(viewsets.ModelViewSet):
    queryset = VisitorIDDocument.objects.all(); serializer_class = VisitorIDDocumentSerializer
    filterset_fields = ("visitor",)


class VisitRequestViewSet(viewsets.ModelViewSet):
    queryset = VisitRequest.objects.select_related(
        "visitor", "site", "host_employee", "purpose",
    ).all()
    serializer_class = VisitRequestSerializer
    filterset_fields = ("status", "mode", "site", "host_employee", "tenant")

    @action(detail=False, methods=["post"], url_path="walk-in")
    def walk_in(self, request):
        s = WalkInCheckInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        visitor, _ = Visitor.objects.get_or_create(
            tenant_id=request.user.tenant_id,
            id_number=d.get("visitor_id_number") or "",
            defaults={
                "first_name": d["visitor_first_name"],
                "last_name": d["visitor_last_name"],
                "phone": d.get("visitor_phone", ""),
            },
        )
        vr = VisitRequest.objects.create(
            tenant_id=request.user.tenant_id,
            visitor=visitor,
            site_id=d["site"],
            host_employee_id=d.get("host_employee"),
            purpose_id=d.get("purpose"),
            purpose_other=d.get("purpose_other", ""),
            mode="walk_in",
            status="checked_in",
            expected_duration_minutes=d["expected_duration_minutes"],
        )
        VisitLog.objects.create(
            visit_request=vr,
            checked_in_at=timezone.now(),
            checkin_user=request.user,
        )
        VisitorPass.objects.create(
            visit_request=vr,
            type="walk_in_pvc",
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(minutes=d["expected_duration_minutes"]),
        )
        return Response(VisitRequestSerializer(vr).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        vr = self.get_object()
        log = vr.logs.filter(checked_out_at__isnull=True).first()
        if log:
            log.checked_out_at = timezone.now()
            log.save(update_fields=["checked_out_at"])
        vr.status = "completed"; vr.save(update_fields=["status"])
        return Response(VisitRequestSerializer(vr).data)


class VisitorInvitationViewSet(viewsets.ModelViewSet):
    queryset = VisitorInvitation.objects.all(); serializer_class = VisitorInvitationSerializer
    filterset_fields = ("visit_request",)


class VisitorPassViewSet(viewsets.ModelViewSet):
    queryset = VisitorPass.objects.all(); serializer_class = VisitorPassSerializer
    filterset_fields = ("visit_request", "type")


class VisitLogViewSet(viewsets.ModelViewSet):
    queryset = VisitLog.objects.select_related("visit_request").all()
    serializer_class = VisitLogSerializer


class WatchlistViewSet(viewsets.ModelViewSet):
    queryset = Watchlist.objects.all(); serializer_class = WatchlistSerializer
    filterset_fields = ("tenant", "site", "is_active")
    search_fields = ("full_name", "id_number")
