from django.http import Http404, HttpResponse
from django.utils import timezone
from django.views import View
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Badge, BadgeAssignment, BadgeHelmetPairing, Device, DeviceHeartbeat,
    DeviceMaintenance, DeviceModel, FirmwareVersion, Helmet, OTAUpdate,
)
from .serializers import (
    BadgeHelmetPairingSerializer, BadgeSerializer, DeviceHeartbeatSerializer,
    DeviceMaintenanceSerializer, DeviceModelSerializer, DeviceSerializer,
    FirmwareVersionSerializer, HelmetSerializer, OTAUpdateSerializer,
)


class DeviceModelViewSet(viewsets.ModelViewSet):
    queryset = DeviceModel.objects.all(); serializer_class = DeviceModelSerializer
    search_fields = ("brand", "model"); filterset_fields = ("type", "is_active")


class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.select_related("tenant", "model", "site", "zone", "checkpoint").all()
    serializer_class = DeviceSerializer
    search_fields = ("serial_number",)
    filterset_fields = ("tenant", "site", "model", "status")

    @action(detail=True, methods=["post"])
    def heartbeat(self, request, pk=None):
        device = self.get_object()
        DeviceHeartbeat.objects.create(
            device=device,
            is_online=request.data.get("is_online", True),
            battery_level=request.data.get("battery_level"),
            signal_strength=request.data.get("signal_strength"),
            payload=request.data.get("payload", {}),
        )
        device.last_heartbeat_at = timezone.now()
        device.battery_level = request.data.get("battery_level", device.battery_level)
        device.save(update_fields=["last_heartbeat_at", "battery_level"])
        return Response({"status": "ok"})


class BadgeViewSet(viewsets.ModelViewSet):
    queryset = Badge.objects.all(); serializer_class = BadgeSerializer
    search_fields = ("uid",)
    filterset_fields = ("tenant", "type", "status", "holder_kind")

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        badge = self.get_object()
        badge.status = "revoked"
        badge.revoked_at = timezone.now()
        badge.revoked_reason = request.data.get("reason", "")
        badge.save(update_fields=["status", "revoked_at", "revoked_reason"])
        return Response({"status": badge.status})


class HelmetViewSet(viewsets.ModelViewSet):
    queryset = Helmet.objects.select_related("tenant", "current_worker").all()
    serializer_class = HelmetSerializer
    search_fields = ("serial_number", "uhf_tag_uid", "ble_beacon_uid")
    filterset_fields = ("tenant", "status")


class BadgeHelmetPairingViewSet(viewsets.ModelViewSet):
    queryset = BadgeHelmetPairing.objects.select_related("worker", "badge", "helmet", "site").all()
    serializer_class = BadgeHelmetPairingSerializer
    filterset_fields = ("worker", "site", "pairing_date", "is_broken")


class DeviceHeartbeatViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceHeartbeat.objects.select_related("device").all()
    serializer_class = DeviceHeartbeatSerializer
    filterset_fields = ("device", "is_online")


class DeviceMaintenanceViewSet(viewsets.ModelViewSet):
    queryset = DeviceMaintenance.objects.all(); serializer_class = DeviceMaintenanceSerializer
    filterset_fields = ("device", "kind")


class FirmwareVersionViewSet(viewsets.ModelViewSet):
    queryset = FirmwareVersion.objects.all(); serializer_class = FirmwareVersionSerializer
    filterset_fields = ("device_model", "is_published")


class OTAUpdateViewSet(viewsets.ModelViewSet):
    queryset = OTAUpdate.objects.select_related("device", "firmware").all()
    serializer_class = OTAUpdateSerializer
    filterset_fields = ("device", "status")


# ===========================================================================
# Badge endpoints — PDF / Thumbnail / Workflow / Lifecycle / Lookup
# ===========================================================================
class BadgePDFDownloadView(View):
    """GET /badges/<pk>/pdf/ — sert le PDF du badge (régénère si absent)."""

    def get(self, request, pk):
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            raise Http404("Badge introuvable")

        from .services import BadgePDFService
        pdf_bytes = BadgePDFService.generate(badge)
        BadgePDFService.generate_and_save(badge)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"badge_{badge.category}_{badge.uid}.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class BadgeThumbnailView(View):
    """GET /badges/<pk>/thumbnail/ — sert l'image PNG du badge."""

    def get(self, request, pk):
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            raise Http404("Badge introuvable")

        from django.core.files.base import ContentFile
        from .services import BadgeThumbnailService

        if not badge.thumbnail or not badge.thumbnail.name:
            try:
                png_bytes = BadgeThumbnailService.generate(badge)
                badge.thumbnail.save(
                    f"badge_{badge.category}_{badge.uid}.png",
                    ContentFile(png_bytes), save=True,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("thumbnail failed")
                return HttpResponse(f"Erreur: {e}", status=500)

        with badge.thumbnail.open("rb") as f:
            data = f.read()
        response = HttpResponse(data, content_type="image/png")
        response["Cache-Control"] = "private, max-age=3600"
        return response


class BadgeIssueWorkflowAPIView(APIView):
    """POST /api/v1/devices/badges/issue/ — Body: {workflow, ...}"""
    permission_classes = [AllowAny]

    def post(self, request):
        from .services import BadgeWorkflowService
        wf = (request.data or {}).get("workflow")

        try:
            if wf == "visitor_qr_pool":
                count = int(request.data.get("count", 10))
                badges = BadgeWorkflowService.create_visitor_qr_pool(count=count)
                return Response({
                    "created": [{"id": b.id, "uid": b.uid} for b in badges],
                    "total": len(badges),
                }, status=status.HTTP_201_CREATED)

            if wf == "employee":
                from employees.models import Employee
                emp = Employee.objects.get(pk=request.data["employee_id"])
                helmet = None
                if request.data.get("helmet_id"):
                    helmet = Helmet.objects.get(pk=request.data["helmet_id"])
                badge = BadgeWorkflowService.issue_employee_badge(emp, helmet=helmet)
                return Response({"id": badge.id, "uid": badge.uid,
                                 "category": badge.category}, status=201)

            if wf == "worker":
                from ouvriers.models import Worker
                w = Worker.objects.get(pk=request.data["worker_id"])
                helmet = Helmet.objects.get(pk=request.data["helmet_id"])
                badge = BadgeWorkflowService.issue_worker_badge(w, helmet=helmet)
                return Response({"id": badge.id, "uid": badge.uid,
                                 "category": badge.category}, status=201)

            return Response({"error": "workflow inconnu"}, status=400)
        except (ValueError, Helmet.DoesNotExist) as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("badge workflow failed")
            return Response({"error": str(e)}, status=500)


class _BadgeLifecycleMixin:
    """Mixin qui charge le badge et invoque la méthode `service_method` du service."""
    permission_classes = [AllowAny]
    service_method: str = ""

    def post(self, request, pk):
        from .services import BadgeWorkflowService
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            return Response({"error": "badge introuvable"}, status=404)

        reason = (request.data or {}).get("reason", "")
        user = request.user if request.user.is_authenticated else None
        try:
            method = getattr(BadgeWorkflowService, self.service_method)
            if self.service_method == "reactivate":
                method(badge, by_user=user)
            else:
                method(badge, reason=reason, by_user=user)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        return Response({
            "ok": True, "id": badge.id, "uid": badge.uid,
            "status": badge.status, "status_label": badge.get_status_display(),
        })


class BadgeSuspendAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "suspend"


class BadgeReactivateAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "reactivate"


class BadgeRevokeAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "revoke"


class BadgeLostAPIView(_BadgeLifecycleMixin, APIView):
    service_method = "mark_lost"


class BadgeReleaseAPIView(APIView):
    """POST /api/v1/devices/badges/<pk>/release/ — restitue / libère."""
    permission_classes = [AllowAny]

    def post(self, request, pk):
        from .services import BadgeWorkflowService
        try:
            badge = Badge.objects.get(pk=pk)
        except Badge.DoesNotExist:
            return Response({"error": "badge introuvable"}, status=404)
        user = request.user if request.user.is_authenticated else None
        BadgeWorkflowService.release(badge, by_user=user)
        return Response({"ok": True, "status": badge.status,
                         "status_label": badge.get_status_display()})


class BadgeLookupAPIView(APIView):
    """GET /api/v1/devices/badges/lookup/?q=<uid_ou_qr>"""
    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"error": "paramètre 'q' requis"}, status=400)

        badge = (Badge.objects.filter(uid=q).select_related("paired_helmet").first()
                 or Badge.objects.filter(qr_payload=q).select_related("paired_helmet").first())

        if not badge and "BADGE:" in q:
            try:
                badge_uid = q.split("BADGE:", 1)[1].split("|", 1)[0]
                badge = Badge.objects.filter(uid=badge_uid).select_related("paired_helmet").first()
            except Exception:
                pass

        if not badge:
            return Response({"found": False, "query": q}, status=404)

        holder_label = ""
        if badge.holder:
            holder_label = str(badge.holder)
        elif badge.qr_payload and badge.qr_payload.startswith("VISIT-"):
            holder_label = f"Visite {badge.qr_payload[6:]}"

        return Response({
            "found": True, "id": badge.id, "uid": badge.uid,
            "category": badge.category,
            "category_label": badge.get_category_display(),
            "type": badge.type, "status": badge.status,
            "status_label": badge.get_status_display(),
            "holder_label": holder_label,
            "holder_kind": badge.holder_kind,
            "valid_from": badge.valid_from.isoformat() if badge.valid_from else None,
            "valid_until": badge.valid_until.isoformat() if badge.valid_until else None,
            "is_currently_valid": badge.is_currently_valid,
            "can_be_used": badge.can_be_used,
            "paired_helmet": (badge.paired_helmet.serial_number
                              if badge.paired_helmet else None),
            "last_scan_at": (badge.last_scan_at.isoformat()
                             if badge.last_scan_at else None),
            "scan_count": badge.scan_count,
            "pdf_url": f"/badges/{badge.id}/pdf/",
            "detail_url": f"/badges/{badge.id}/",
        })
