"""KAYDAN SHIELD — access_control: scans, événements, règles, gâche."""
import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimeStampedModel


class AccessEvent(models.Model):
    DIRECTION_CHOICES = [("in", "Entrée"), ("out", "Sortie"), ("pass", "Passage")]
    METHOD_CHOICES = [
        ("nfc", "NFC"), ("uhf", "UHF"), ("ble", "BLE"),
        ("qr", "QR"), ("manual", "Manuel"),
    ]
    DECISION_CHOICES = [
        ("granted", "Accordé"),
        ("denied", "Refusé"),
        ("review", "À vérifier"),
    ]
    HOLDER_KIND_CHOICES = [
        ("employee", "Employé"),
        ("worker", "Ouvrier"),
        ("visitor", "Visiteur"),
        ("unknown", "Inconnu"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    timestamp = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="access_events")
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="access_events")
    zone = models.ForeignKey(
        "sites.Zone", null=True, blank=True, on_delete=models.SET_NULL, related_name="access_events",
    )
    checkpoint = models.ForeignKey(
        "sites.Checkpoint", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="access_events",
    )
    device = models.ForeignKey(
        "devices.Device", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="access_events",
    )
    operator = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="access_events",
        help_text="Utilisateur ayant scanné (cas mode mobile)",
    )

    badge_uid = models.CharField(max_length=64, blank=True, db_index=True)
    helmet_uid = models.CharField(max_length=64, blank=True, db_index=True)

    holder_kind = models.CharField(max_length=12, choices=HOLDER_KIND_CHOICES, default="unknown")
    holder_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    holder_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    holder = GenericForeignKey("holder_content_type", "holder_object_id")

    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, default="in")
    method = models.CharField(max_length=8, choices=METHOD_CHOICES, default="nfc")
    decision = models.CharField(max_length=8, choices=DECISION_CHOICES, default="granted")
    denial_reason = models.CharField(max_length=240, blank=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["site", "timestamp"]),
            models.Index(fields=["badge_uid", "timestamp"]),
            models.Index(fields=["decision", "timestamp"]),
        ]

    def __str__(self): return f"{self.timestamp:%Y-%m-%d %H:%M} · {self.badge_uid} · {self.decision}"


class AccessRule(TimeStampedModel):
    TYPE_CHOICES = [
        ("time_window", "Plage horaire"),
        ("zone_authorization", "Autorisation de zone"),
        ("pairing_required", "Appairage badge/casque requis"),
        ("certification_required", "Certification HSE requise"),
        ("escort_required", "Escorte obligatoire"),
        ("watchlist", "Liste rouge"),
        ("custom", "Règle personnalisée"),
    ]
    SEVERITY_CHOICES = [
        ("info", "Info"), ("warning", "Avertissement"), ("critical", "Critique"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="access_rules")
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.CASCADE, related_name="access_rules",
    )
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=180)
    type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="warning")
    is_active = models.BooleanField(default=True)
    conditions = models.JSONField(default=dict, blank=True)
    actions = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("tenant", "site", "code")
        ordering = ["site", "code"]


class AccessDecision(models.Model):
    """Trace fine de l'évaluation des règles pour un AccessEvent."""

    event = models.OneToOneField(AccessEvent, on_delete=models.CASCADE, related_name="decision_trace")
    rules_evaluated = models.JSONField(default=list, blank=True)
    deciding_rule_code = models.CharField(max_length=80, blank=True)
    risk_score = models.FloatField(default=0.0)
    notes = models.TextField(blank=True)


class DoorCommand(TimeStampedModel):
    COMMAND_CHOICES = [("unlock", "Déverrouiller"), ("lock", "Verrouiller")]
    STATUS_CHOICES = [
        ("queued", "En file"),
        ("sent", "Envoyée"),
        ("acknowledged", "Reçue"),
        ("succeeded", "Succès"),
        ("failed", "Échec"),
    ]

    checkpoint = models.ForeignKey("sites.Checkpoint", on_delete=models.CASCADE, related_name="door_commands")
    device = models.ForeignKey(
        "devices.Device", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="door_commands",
    )
    issued_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="door_commands",
    )
    related_event = models.ForeignKey(
        AccessEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name="door_commands",
    )
    command = models.CharField(max_length=8, choices=COMMAND_CHOICES, default="unlock")
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default="queued")
    reason = models.CharField(max_length=240, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)


class QRCodeToken(TimeStampedModel):
    """Token QR signé pour le visiteur self-service."""

    visit_request = models.ForeignKey(
        "visitors.VisitRequest", on_delete=models.CASCADE, related_name="qr_tokens",
    )
    token = models.CharField(max_length=120, unique=True, default=uuid.uuid4)
    payload = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()
    single_use = models.BooleanField(default=True)
    used_at = models.DateTimeField(null=True, blank=True)
