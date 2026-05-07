"""KAYDAN SHIELD — notifications: templates, canaux, instances, prefs."""
from django.db import models

from core.models import TimeStampedModel


class NotificationTemplate(TimeStampedModel):
    CHANNEL_CHOICES = [
        ("inapp", "In-app"), ("email", "Email"), ("sms", "SMS"),
        ("push", "Push"), ("webhook", "Webhook"), ("whatsapp", "WhatsApp"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant", null=True, blank=True,
        on_delete=models.CASCADE, related_name="notification_templates",
    )
    code = models.SlugField(max_length=80)
    channel = models.CharField(max_length=12, choices=CHANNEL_CHOICES)
    subject = models.CharField(max_length=240, blank=True)
    body = models.TextField()
    variables = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tenant", "code", "channel")
        ordering = ["code"]


class NotificationPreference(TimeStampedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notification_prefs")
    channel = models.CharField(max_length=12, choices=NotificationTemplate.CHANNEL_CHOICES)
    template_code = models.SlugField(max_length=80, blank=True, help_text="vide = global")
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "channel", "template_code")


class Notification(TimeStampedModel):
    STATUS_CHOICES = [
        ("queued", "En file"),
        ("sent", "Envoyée"),
        ("delivered", "Livrée"),
        ("failed", "Échec"),
        ("read", "Lue"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="notifications",
    )
    template = models.ForeignKey(
        NotificationTemplate, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="notifications",
    )
    channel = models.CharField(max_length=12, choices=NotificationTemplate.CHANNEL_CHOICES)
    subject = models.CharField(max_length=240, blank=True)
    body = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "status"])]


class WebSocketSubscription(TimeStampedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ws_subscriptions")
    topic = models.CharField(max_length=120, db_index=True, help_text="ex: site:42:alerts")
    channel_name = models.CharField(max_length=160)
    last_ping_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "topic", "channel_name")
