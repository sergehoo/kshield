"""KAYDAN SHIELD — audit: log immuable, hash chaîné, RGPD."""
import hashlib
import json

from django.db import models

from core.models import TimeStampedModel


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Création"), ("update", "Mise à jour"), ("delete", "Suppression"),
        ("login", "Connexion"), ("logout", "Déconnexion"),
        ("export", "Export"), ("acknowledge", "Acquittement"),
        ("override", "Surcharge manuelle"), ("unlock_door", "Déverrouillage porte"),
        ("api_access", "Accès API"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    tenant = models.ForeignKey(
        "core.Tenant", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_logs",
    )
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_logs",
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    target_model = models.CharField(max_length=120, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)

    previous_hash = models.CharField(max_length=128, blank=True)
    hash = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["target_model", "target_id"])]

    def compute_hash(self) -> str:
        payload = {
            "ts": self.timestamp.isoformat() if self.timestamp else "",
            "user": self.user_id,
            "action": self.action,
            "target": f"{self.target_model}:{self.target_id}",
            "before": self.before,
            "after": self.after,
            "prev": self.previous_hash,
        }
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()


class DataExportRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("processing", "En cours"),
        ("ready", "Prête"),
        ("delivered", "Livrée"),
        ("failed", "Échec"),
    ]
    KIND_CHOICES = [
        ("rgpd_export", "Export RGPD"),
        ("rgpd_forget", "Effacement RGPD"),
        ("operational", "Export opérationnel"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="export_requests")
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="export_requests",
    )
    subject_holder_kind = models.CharField(max_length=12, blank=True)
    subject_holder_id = models.PositiveBigIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default="operational")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    parameters = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to="exports/", null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class LegalRetentionPolicy(TimeStampedModel):
    """Durée de conservation par type de donnée (ex: AccessEvent → 5 ans)."""

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="retention_policies")
    target_model = models.CharField(max_length=120)
    retention_days = models.PositiveIntegerField()
    legal_basis = models.CharField(max_length=240, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tenant", "target_model")


class ConformityRegister(TimeStampedModel):
    """Registre des contrôles obligatoires (extincteurs, exercices, etc.)."""

    KIND_CHOICES = [
        ("evacuation_drill", "Exercice d'évacuation"),
        ("equipment_check", "Contrôle équipement"),
        ("inspection", "Inspection"),
        ("audit", "Audit"),
        ("other", "Autre"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="conformity_registers")
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="conformity_registers",
    )
    kind = models.CharField(max_length=24, choices=KIND_CHOICES)
    title = models.CharField(max_length=240)
    performed_at = models.DateTimeField()
    performed_by = models.CharField(max_length=240, blank=True)
    result = models.TextField(blank=True)
    document = models.FileField(upload_to="conformity/", null=True, blank=True)
