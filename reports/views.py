from rest_framework import viewsets

from .models import Dashboard, DashboardWidget, KPISnapshot, Report, ReportRun, ReportSchedule
from .serializers import (
    DashboardSerializer, DashboardWidgetSerializer, KPISnapshotSerializer,
    ReportRunSerializer, ReportScheduleSerializer, ReportSerializer,
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
