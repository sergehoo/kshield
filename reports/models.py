"""KAYDAN SHIELD — reports: rapports, KPI snapshots, dashboards."""
from django.db import models

from core.models import TimeStampedModel


class Report(TimeStampedModel):
    TYPE_CHOICES = [
        ("tabular", "Tableau"), ("chart", "Graphique"),
        ("dashboard", "Tableau de bord"), ("pdf_export", "Export PDF"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="reports")
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=80)
    type = models.CharField(max_length=14, choices=TYPE_CHOICES, default="tabular")
    description = models.TextField(blank=True)
    query = models.JSONField(default=dict, blank=True, help_text="Définition paramétrée")
    scope = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["name"]


class ReportRun(TimeStampedModel):
    STATUS_CHOICES = [
        ("queued", "En file"), ("running", "En cours"),
        ("succeeded", "Réussi"), ("failed", "Échec"), ("expired", "Expiré"),
    ]
    FORMAT_CHOICES = [("xlsx", "XLSX"), ("pdf", "PDF"), ("csv", "CSV"), ("json", "JSON")]

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="runs")
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="report_runs",
    )
    parameters = models.JSONField(default=dict, blank=True)
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default="xlsx")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    file = models.FileField(upload_to="reports/runs/", null=True, blank=True)
    error_message = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class ReportSchedule(TimeStampedModel):
    FREQUENCY_CHOICES = [
        ("daily", "Quotidien"), ("weekly", "Hebdomadaire"),
        ("monthly", "Mensuel"), ("custom", "Personnalisé (cron)"),
    ]

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="schedules")
    frequency = models.CharField(max_length=12, choices=FREQUENCY_CHOICES, default="daily")
    cron_expression = models.CharField(max_length=80, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    recipients = models.ManyToManyField("accounts.User", blank=True, related_name="report_schedules")
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)


class KPISnapshot(TimeStampedModel):
    """Agrégations quotidiennes pré-calculées (évite les heavy queries)."""

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="kpi_snapshots")
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.CASCADE, related_name="kpi_snapshots",
    )
    date = models.DateField(db_index=True)

    presence_rate = models.FloatField(default=0.0)
    avg_delay_minutes = models.FloatField(default=0.0)
    total_punches = models.PositiveIntegerField(default=0)
    total_workers = models.PositiveIntegerField(default=0)
    total_employees = models.PositiveIntegerField(default=0)
    total_visitors = models.PositiveIntegerField(default=0)
    open_alerts = models.PositiveIntegerField(default=0)
    confirmed_frauds = models.PositiveIntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("tenant", "site", "date")
        ordering = ["-date"]


class Dashboard(TimeStampedModel):
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="dashboards")
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=80)
    layout = models.JSONField(default=dict, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ("tenant", "code")


class DashboardWidget(TimeStampedModel):
    KIND_CHOICES = [
        ("kpi", "KPI"), ("line_chart", "Courbe"), ("bar_chart", "Barres"),
        ("table", "Tableau"), ("map", "Carte"), ("heatmap", "Heatmap"), ("alerts_feed", "Flux d'alertes"),
    ]
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    kind = models.CharField(max_length=14, choices=KIND_CHOICES)
    title = models.CharField(max_length=180)
    query = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    position = models.JSONField(default=dict, blank=True)  # x, y, w, h
