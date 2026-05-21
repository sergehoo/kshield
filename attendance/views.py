from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.hmac_auth import HMACAPIKeyAuthentication
from accounts.permissions import IsAuthenticatedOrAPIKey
from accounts.rbac import HasKshieldPermission

from .models import (
    AttendanceCorrection, AttendanceDay, BLEPresencePing, BLEPresenceWindow,
    LeaveRequest, OvertimeCalculation, OvertimeRule, Punch, Roster,
)
from .serializers import (
    AttendanceCorrectionSerializer, AttendanceDaySerializer, BLEPresencePingSerializer,
    BLEPresenceWindowSerializer, LeaveRequestSerializer, OvertimeCalculationSerializer,
    OvertimeRuleSerializer, PunchSerializer, RosterSerializer,
)


class PunchViewSet(viewsets.ModelViewSet):
    queryset = Punch.objects.select_related("site", "source_event").all()
    serializer_class = PunchSerializer
    filterset_fields = ("tenant", "site", "type", "status", "holder_kind")
    ordering_fields = ("timestamp",)
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class AttendanceDayViewSet(viewsets.ModelViewSet):
    queryset = AttendanceDay.objects.select_related("site").all()
    serializer_class = AttendanceDaySerializer
    filterset_fields = ("tenant", "site", "status", "date", "holder_kind")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class BLEPresencePingViewSet(viewsets.ModelViewSet):
    """Ingestion BLE — accepte HMAC (casques) ou JWT (back-office)."""
    queryset = BLEPresencePing.objects.select_related("helmet", "zone").all()
    serializer_class = BLEPresencePingSerializer
    filterset_fields = ("helmet", "zone", "is_immobile")
    authentication_classes = [HMACAPIKeyAuthentication, JWTAuthentication]
    # Note : un AnonymousUser arrivé via HMAC sera autorisé par HasKshieldPermission
    # (vérifie request.auth APIKey). Les JWT users ont besoin de attendance.view.
    permission_classes = [IsAuthenticatedOrAPIKey, HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.view",
                      "batch_ingest": "attendance.view"}

    @action(detail=False, methods=["post"], url_path="batch")
    def batch_ingest(self, request):
        """POST /api/v1/attendance/ble-pings/batch/ — ingestion bulk haute fréquence.

        Body : {"pings": [{"helmet_uid", "timestamp", "rssi", "is_immobile",
                            "accelerometer_payload"}, ...]} (max 500 par batch)

        Modes :
          - synchrone (par défaut) : bulk_create immédiat, renvoie le compte.
          - async : ``?async=1`` ou batch >= 200 → délègue à Celery
            ``attendance.ingest_ble_batch`` (réponse 202 immédiate, retries auto).
        """
        from devices.models import Helmet
        pings = (request.data.get("pings") or [])[:500]
        if not pings:
            return Response({"error": "Aucun ping fourni (champ 'pings' attendu)"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Dispatch async si gros batch ou si demandé explicitement
        wants_async = (request.query_params.get("async") in ("1", "true", "yes")
                       or len(pings) >= 200)
        if wants_async:
            try:
                from attendance.tasks import ingest_ble_batch
                task = ingest_ble_batch.delay(pings)
                return Response({
                    "queued": True, "count": len(pings), "task_id": task.id,
                }, status=status.HTTP_202_ACCEPTED)
            except Exception:
                # Si broker injoignable, fallback sync (évite la perte de pings)
                pass

        # Bulk lookup helmets par uhf_tag_uid (cache mem)
        uids = {p.get("helmet_uid") for p in pings if p.get("helmet_uid")}
        helmets = {h.uhf_tag_uid: h for h in Helmet.objects.filter(
            uhf_tag_uid__in=uids
        )}

        objects = []
        skipped = 0
        for p in pings:
            uid = p.get("helmet_uid")
            helmet = helmets.get(uid)
            if not helmet:
                skipped += 1
                continue
            objects.append(BLEPresencePing(
                helmet=helmet,
                timestamp=p.get("timestamp"),
                rssi=p.get("rssi"),
                is_immobile=bool(p.get("is_immobile", False)),
                accelerometer_payload=p.get("accelerometer_payload") or {},
            ))
        # bulk_create plus rapide que create() x N
        BLEPresencePing.objects.bulk_create(objects, batch_size=500)
        return Response({
            "ingested": len(objects),
            "skipped": skipped,
            "unknown_helmets": list(uids - set(helmets.keys()))[:10],
        }, status=status.HTTP_201_CREATED)


class BLEPresenceWindowViewSet(viewsets.ModelViewSet):
    queryset = BLEPresenceWindow.objects.all(); serializer_class = BLEPresenceWindowSerializer
    filterset_fields = ("helmet", "zone")


class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.all(); serializer_class = LeaveRequestSerializer
    filterset_fields = ("employee", "worker", "type", "status")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}


class RosterViewSet(viewsets.ModelViewSet):
    queryset = Roster.objects.all(); serializer_class = RosterSerializer
    filterset_fields = ("tenant", "site", "date", "holder_kind")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "site__company")


class OvertimeRuleViewSet(viewsets.ModelViewSet):
    queryset = OvertimeRule.objects.all(); serializer_class = OvertimeRuleSerializer
    filterset_fields = ("company", "is_active")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}

    def get_queryset(self):
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "company")


class OvertimeCalculationViewSet(viewsets.ModelViewSet):
    queryset = OvertimeCalculation.objects.all(); serializer_class = OvertimeCalculationSerializer
    filterset_fields = ("employee", "worker", "week_start")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}


class AttendanceCorrectionViewSet(viewsets.ModelViewSet):
    queryset = AttendanceCorrection.objects.all(); serializer_class = AttendanceCorrectionSerializer
    filterset_fields = ("attendance_day", "performed_by")
    permission_classes = [HasKshieldPermission]
    kshield_perms = {"read": "attendance.view", "write": "attendance.correct"}
