from django.contrib import admin

from .models import (Dashboard, DashboardWidget, ExecutiveDigest, KPISnapshot,
                       Report, ReportRun, ReportSchedule)

admin.site.register([Report, ReportRun, ReportSchedule, KPISnapshot, Dashboard, DashboardWidget])


@admin.register(ExecutiveDigest)
class ExecutiveDigestAdmin(admin.ModelAdmin):
    list_display = ("period", "period_start", "period_end", "status",
                     "title", "model_used", "tokens_used", "sent_at")
    list_filter = ("period", "status", "tenant")
    search_fields = ("title", "executive_summary")
    readonly_fields = ("raw_metrics", "top_alerts", "kpi_deltas",
                         "anomalies", "recommendations",
                         "tokens_used", "generation_seconds", "model_used",
                         "sent_at", "sent_to")
    ordering = ("-period_start",)
