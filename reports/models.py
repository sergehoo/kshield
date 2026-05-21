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


# ---------------------------------------------------------------------------
# Digest hebdomadaire IA — résumé exécutif généré chaque lundi matin
# ---------------------------------------------------------------------------
class ExecutiveDigest(TimeStampedModel):
    """Résumé exécutif hebdo généré par LLM (OpenAI, Mistral, etc).

    Contenu :
      - top_alerts : 5 alertes anti-fraude les plus critiques de la semaine
      - kpi_deltas : variations clés vs semaine précédente
      - anomalies : patterns inhabituels détectés par l'IA
      - recommendations : 3-5 actions concrètes suggérées

    Diffusé par email aux abonnés (rôles configurés) chaque lundi 07h.
    """

    PERIOD_CHOICES = [
        ("weekly", "Hebdomadaire"),
        ("monthly", "Mensuel"),
        ("quarterly", "Trimestriel"),
    ]
    STATUS_CHOICES = [
        ("queued", "En file"), ("generating", "Génération"),
        ("ready", "Prêt"), ("failed", "Échec"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE,
                                 related_name="executive_digests")
    period = models.CharField(max_length=12, choices=PERIOD_CHOICES, default="weekly")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField()

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="queued")

    raw_metrics = models.JSONField(default=dict, blank=True,
        help_text="Snapshot des KPI utilisés pour générer le digest.")

    title = models.CharField(max_length=240, blank=True)
    executive_summary = models.TextField(blank=True,
        help_text="2-3 paragraphes destinés au CEO/COO.")
    top_alerts = models.JSONField(default=list, blank=True)
    kpi_deltas = models.JSONField(default=list, blank=True)
    anomalies = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)

    model_used = models.CharField(max_length=80, blank=True)
    tokens_used = models.IntegerField(default=0)
    generation_seconds = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-period_start",)
        unique_together = ("tenant", "period", "period_start")
        indexes = [
            models.Index(fields=["status", "-period_start"]),
        ]

    def __str__(self):
        return f"Digest {self.period} {self.period_start} ({self.status})"
