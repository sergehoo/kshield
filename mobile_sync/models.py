"""KAYDAN SHIELD — mobile_sync: PDA / smartphones / tablettes mobiles."""
import uuid

from django.db import models

from core.models import TimeStampedModel


class MobileDevice(TimeStampedModel):
    """Terminal mobile enrôlé (PDA Chainway, tablette, smartphone agent pointage)."""

    STATUS_CHOICES = [
        ("active", "Actif"), ("inactive", "Inactif"), ("revoked", "Révoqué"),
    ]
    OS_CHOICES = [("android", "Android"), ("ios", "iOS"), ("other", "Autre")]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="mobile_devices")
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mobile_devices",
    )
    device_id = models.CharField(max_length=120, unique=True, db_index=True)
    name = models.CharField(max_length=180, blank=True)
    os = models.CharField(max_length=12, choices=OS_CHOICES, default="android")
    os_version = models.CharField(max_length=40, blank=True)
    app_version = models.CharField(max_length=40, blank=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mobile_devices",
    )
    api_key = models.ForeignKey(
        "accounts.APIKey", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mobile_devices",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    enrolled_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)


class OfflineScanQueue(models.Model):
    """Scan capturé hors connexion, en attente de synchronisation."""

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("synced", "Synchronisé"),
        ("rejected", "Rejeté"),
        ("duplicate", "Doublon"),
    ]

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE, related_name="offline_queue")
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    captured_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    synced_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=240, blank=True)
    resulting_event_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-captured_at"]
        indexes = [models.Index(fields=["device", "status"])]


class SyncSession(TimeStampedModel):
    """Session de synchronisation (pull + push)."""

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE, related_name="sync_sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    pulled_count = models.PositiveIntegerField(default=0)
    pushed_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)


class MobileBundle(TimeStampedModel):
    """Paquet de données préparé pour un terminal mobile (delta)."""

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE, related_name="bundles")
    since = models.DateTimeField()
    payload = models.JSONField(default=dict, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
