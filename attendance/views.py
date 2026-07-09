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


class AttendanceSummaryView(APIView):
    """GET /api/v1/attendance/summary/today/ — KPIs journée pour le dashboard React.

    Retourne un JSON compact avec les compteurs clés :
        {
          "date": "2026-07-07",
          "present_count": 42,
          "absent_count": 5,
          "late_count": 3,
          "total_workers": 50,
          "events_24h": 187,
          "total_overtime_minutes": 145,
        }

    Multi-tenant strict : ne compte que les données du tenant de l'utilisateur.
    Cache Redis 60s pour éviter de recalculer 4 fois/min quand plusieurs users
    ouvrent le dashboard simultanément.
    """
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import logging
        from datetime import date, timedelta
        from django.core.cache import cache
        from django.db.models import Count, Sum, Q
        from django.utils import timezone

        logger = logging.getLogger(__name__)

        today = date.today()
        yesterday_dt = timezone.now() - timedelta(hours=24)

        # Cache clé par tenant + date (invalide auto à minuit)
        tenant_id = getattr(request.user, "tenant_id", None) or "public"
        cache_key = f"att_summary:{tenant_id}:{today.isoformat()}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        # Réponse minimale par défaut — remplie best-effort ci-dessous.
        agg = {"total": 0, "present": 0, "late": 0, "absent": 0, "total_overtime": 0}
        events_24h = 0
        total_workers = 0

        # Scope tenant : on filtre par site__company__tenant si dispo
        try:
            from accounts.scoping import scope_queryset_by_company

            days_qs = scope_queryset_by_company(
                AttendanceDay.objects.filter(date=today),
                request.user,
                "site__company",
            )

            agg = days_qs.aggregate(
                total=Count("id"),
                present=Count("id", filter=Q(status__in=["present", "partial"])),
                late=Count("id", filter=Q(status="late")),
                absent=Count("id", filter=Q(status="absent")),
                total_overtime=Sum("overtime_minutes"),
            )
        except Exception as exc:
            logger.exception("AttendanceSummary — agrégation KO : %s", exc)

        # Événements 24h — via AccessEvent (import late pour éviter cycle)
        try:
            from access_control.models import AccessEvent
            events_qs = scope_queryset_by_company(
                AccessEvent.objects.filter(timestamp__gte=yesterday_dt),
                request.user,
                "site__company",
            )
            events_24h = events_qs.count()
        except Exception:
            events_24h = 0

        # Total ouvriers connus (pour le ratio X/Y)
        try:
            from ouvriers.models import Worker
            total_workers = scope_queryset_by_company(
                Worker.objects.filter(is_active=True),
                request.user,
                "site__company",
            ).count()
        except Exception:
            total_workers = agg.get("total") or 0

        data = {
            "date": today.isoformat(),
            "present_count": agg.get("present") or 0,
            "absent_count": agg.get("absent") or 0,
            "late_count": agg.get("late") or 0,
            "total_workers": total_workers,
            "events_24h": events_24h,
            "total_overtime_minutes": int(agg.get("total_overtime") or 0),
        }
        cache.set(cache_key, data, 60)
        return Response(data)


class AttendancePresenceLiveView(APIView):
    """GET /api/v1/attendance/presence/live/ — snapshot 'qui est présent maintenant'.

    Utilise la dernière direction (in/out) par ouvrier pour déterminer sa présence
    à cet instant. Ne renvoie que les 50 premiers pour rester léger côté dashboard.
    """
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        try:
            from access_control.models import AccessEvent
            from accounts.scoping import scope_queryset_by_company

            since = timezone.now() - timedelta(hours=16)
            qs = scope_queryset_by_company(
                AccessEvent.objects.filter(
                    timestamp__gte=since,
                    decision="granted",
                ).order_by("holder_object_id", "-timestamp"),
                request.user,
                "site__company",
            )
            latest_by_holder = {}
            for e in qs.iterator():
                key = (e.holder_content_type_id, e.holder_object_id)
                if key not in latest_by_holder:
                    latest_by_holder[key] = e

            present = [e for e in latest_by_holder.values() if e.direction == "in"]
            return Response({
                "count": len(present),
                "as_of": timezone.now().isoformat(),
                "sample": [
                    {
                        "holder_name": getattr(e, "holder_name", None) or e.badge_uid,
                        "site": getattr(e.site, "name", None) if e.site_id else None,
                        "since": e.timestamp,
                    }
                    for e in present[:50]
                ],
            })
        except Exception as exc:
            return Response({"count": 0, "error": str(exc)[:200]}, status=200)
