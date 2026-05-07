"""KAYDAN SHIELD — antifraud: règles + alertes + investigations + scoring."""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimeStampedModel


class FraudRule(TimeStampedModel):
    SEVERITY_CHOICES = [
        ("info", "Info"), ("warning", "Avertissement"), ("critical", "Critique"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="fraud_rules")
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=180)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="warning")
    is_active = models.BooleanField(default=True)
    parameters = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["code"]

    def __str__(self): return f"{self.code} ({self.severity})"


class FraudAlert(TimeStampedModel):
    STATUS_CHOICES = [
        ("open", "Ouverte"),
        ("acknowledged", "Prise en compte"),
        ("confirmed", "Confirmée fraude"),
        ("dismissed", "Écartée"),
        ("escalated", "Escaladée"),
    ]
    HOLDER_KIND_CHOICES = [
        ("employee", "Employé"), ("worker", "Ouvrier"),
        ("visitor", "Visiteur"), ("unknown", "Inconnu"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="fraud_alerts")
    rule = models.ForeignKey(FraudRule, on_delete=models.PROTECT, related_name="alerts")
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.SET_NULL, related_name="fraud_alerts",
    )
    raised_at = models.DateTimeField(db_index=True)

    primary_holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES, default="unknown")
    primary_holder_id = models.PositiveBigIntegerField(null=True, blank=True)
    secondary_holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES, blank=True)
    secondary_holder_id = models.PositiveBigIntegerField(null=True, blank=True)

    related_event = models.ForeignKey(
        "access_control.AccessEvent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="fraud_alerts",
    )
    evidence = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=10, choices=FraudRule.SEVERITY_CHOICES, default="warning")

    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default="open", db_index=True)
    assigned_to = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="assigned_fraud_alerts",
    )
    resolution_comment = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="resolved_fraud_alerts",
    )

    class Meta:
        ordering = ["-raised_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "severity"]),
            models.Index(fields=["site", "raised_at"]),
        ]

    def __str__(self): return f"{self.rule.code} · {self.status}"


class FraudInvestigation(TimeStampedModel):
    STATUS_CHOICES = [
        ("open", "Ouverte"),
        ("in_progress", "En cours"),
        ("closed", "Fermée"),
    ]
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="investigations")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default="open")
    alerts = models.ManyToManyField(FraudAlert, blank=True, related_name="investigations")
    opened_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="investigations_opened",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    conclusion = models.TextField(blank=True)


class FraudScoring(TimeStampedModel):
    """Score de risque rolling 30 jours par holder."""

    HOLDER_KIND_CHOICES = [("employee", "Employé"), ("worker", "Ouvrier"), ("visitor", "Visiteur")]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="fraud_scores")
    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES)
    holder_object_id = models.PositiveBigIntegerField()
    score = models.FloatField(default=0.0)
    breakdown = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(db_index=True)

    class Meta:
        unique_together = ("tenant", "holder_kind", "holder_object_id")


class BLEStillnessSignal(TimeStampedModel):
    """Signal levé quand un casque est immobile au-delà du seuil."""

    helmet = models.ForeignKey("devices.Helmet", on_delete=models.CASCADE, related_name="stillness_signals")
    zone = models.ForeignKey("sites.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="stillness_signals")
    detected_at = models.DateTimeField(db_index=True)
    immobile_minutes = models.PositiveIntegerField()
    cleared_at = models.DateTimeField(null=True, blank=True)
