from rest_framework import serializers

from .models import (Dashboard, DashboardWidget, ExecutiveDigest, KPISnapshot,
                       Report, ReportRun, ReportSchedule)


class ReportSerializer(serializers.ModelSerializer):
    class Meta: model = Report; fields = "__all__"


class ReportRunSerializer(serializers.ModelSerializer):
    class Meta: model = ReportRun; fields = "__all__"


class ReportScheduleSerializer(serializers.ModelSerializer):
    class Meta: model = ReportSchedule; fields = "__all__"


class KPISnapshotSerializer(serializers.ModelSerializer):
    class Meta: model = KPISnapshot; fields = "__all__"


class DashboardSerializer(serializers.ModelSerializer):
    class Meta: model = Dashboard; fields = "__all__"


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta: model = DashboardWidget; fields = "__all__"


class ExecutiveDigestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutiveDigest
        fields = "__all__"
        read_only_fields = (
            "raw_metrics", "title", "executive_summary", "top_alerts",
            "kpi_deltas", "anomalies", "recommendations",
            "model_used", "tokens_used", "generation_seconds",
            "sent_at", "sent_to", "status", "error_message",
        )
