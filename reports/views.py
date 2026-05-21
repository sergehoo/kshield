from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (Dashboard, DashboardWidget, ExecutiveDigest, KPISnapshot,
                       Report, ReportRun, ReportSchedule)
from .serializers import (
    DashboardSerializer, DashboardWidgetSerializer, ExecutiveDigestSerializer,
    KPISnapshotSerializer, ReportRunSerializer, ReportScheduleSerializer,
    ReportSerializer,
)


class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all(); serializer_class = ReportSerializer
    filterset_fields = ("tenant", "type", "is_active")


class ReportRunViewSet(viewsets.ModelViewSet):
    queryset = ReportRun.objects.all(); serializer_class = ReportRunSerializer
    filterset_fields = ("report", "status", "format", "requested_by")


class ReportScheduleViewSet(viewsets.ModelViewSet):
    queryset = ReportSchedule.objects.all(); serializer_class = ReportScheduleSerializer
    filterset_fields = ("report", "frequency", "is_active")


class KPISnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = KPISnapshot.objects.all(); serializer_class = KPISnapshotSerializer
    filterset_fields = ("tenant", "site", "date")


class DashboardViewSet(viewsets.ModelViewSet):
    queryset = Dashboard.objects.all(); serializer_class = DashboardSerializer
    filterset_fields = ("tenant", "is_default")


class DashboardWidgetViewSet(viewsets.ModelViewSet):
    queryset = DashboardWidget.objects.all(); serializer_class = DashboardWidgetSerializer
    filterset_fields = ("dashboard", "kind")


class ExecutiveDigestViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule — la création/maj passe par les tâches Celery."""
    queryset = ExecutiveDigest.objects.select_related("tenant").order_by("-period_start")
    serializer_class = ExecutiveDigestSerializer
    filterset_fields = ("tenant", "period", "status")

    @action(detail=False, methods=["post"], url_path="generate")
    def generate_now(self, request):
        """Déclenche la génération d'un digest à la demande.

        Body JSON : {"tenant_id": int, "period": "weekly|monthly|quarterly"}
        """
        tenant_id = request.data.get("tenant_id")
        period = request.data.get("period", "weekly")
        if not tenant_id:
            return Response({"error": "tenant_id requis"}, status=400)
        try:
            from reports.tasks import generate_digest_for_tenant
            generate_digest_for_tenant.delay(int(tenant_id), period=period,
                                              send_email=False)
            return Response({"status": "queued"})
        except Exception as exc:
            return Response({"error": str(exc)[:200]}, status=500)

    @action(detail=True, methods=["post"], url_path="regenerate")
    def regenerate(self, request, pk=None):
        from reports.tasks import regenerate_digest
        regenerate_digest.delay(int(pk), send_email=bool(request.data.get("send_email")))
        return Response({"status": "queued"})
