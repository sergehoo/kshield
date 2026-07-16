"""KAYDAN SHIELD — Modèles d'événements techniques.

Phase 1.1 de la refonte des événements en direct.

Architecture :
  - EventType       : nomenclature paramétrable (69 types listés dans le
                       cahier des charges + extensible via back-office).
  - DeviceEvent     : événement technique unifié (device / gateway / agent /
                       sync / sécurité). Complète AccessEvent (métier accès)
                       sans le remplacer.
  - EventAcknowledgement : traçabilité des acquittements + résolutions
                            par utilisateur, non modifiable après création.

Le tout est indexé pour les filtres du cahier des charges :
    site, zone, type, severity, gateway, agent, date, is_synced, is_offline.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from core.mixins import TimeStampedModel


# ═══════════════════════════════════════════════════════════════════
# EventType — nomenclature paramétrable
# ═══════════════════════════════════════════════════════════════════
class EventCategory(models.TextChoices):
    """8 grandes catégories métier — pour grouper dans les filtres."""
    ACCESS      = "access",      "Contrôle d'accès"
    ATTENDANCE  = "attendance",  "Pointage"
    RFID        = "rfid",        "RFID / NFC"
    BLE         = "ble",         "BLE / Casques"
    DEVICE      = "device",      "Équipements"
    GATEWAY     = "gateway",     "Gateway & Agents"
    SECURITY    = "security",    "Sécurité"
    SYSTEM      = "system",      "Système"


class EventSeverity(models.TextChoices):
    """4 niveaux de criticité — mappés aux couleurs UI et alertes."""
    INFO       = "info",      "Information"
    WARNING    = "warning",   "Avertissement"
    CRITICAL   = "critical",  "Critique"
    EMERGENCY  = "emergency", "Urgence"


class EventResult(models.TextChoices):
    """Résultat métier du cahier des charges section 1.1."""
    GRANTED    = "granted",   "Autorisé"
    DENIED     = "denied",    "Refusé"
    PENDING    = "pending",   "En attente"
    ANOMALY    = "anomaly",   "Anomalie"
    ALERT      = "alert",     "Alerte"
    NEUTRAL    = "neutral",   "Neutre"    # pour events techniques (sync, etc.)


class TransmissionMode(models.TextChoices):
    """Mode de remontée — section 1.1 du cahier des charges."""
    REALTIME_CLOUD = "realtime_cloud", "Temps réel Cloud"
    GATEWAY_LOCAL  = "gateway_local",  "Gateway locale"
    DEFERRED_SYNC  = "deferred_sync",  "Synchronisation différée"
    OFFLINE        = "offline",        "Événement offline"


class EventType(TimeStampedModel):
    """Nomenclature paramétrable des types d'événements.

    Peuplée initialement par le management command ``seed_event_types``
    avec les 69 types du cahier des charges. Ensuite administrable via
    Django admin par les superusers pour ajouter des types custom
    (ex: événements métier spécifiques à un client).

    Le champ ``code`` est stable (immutable) et sert de clé technique
    pour matcher les événements entrants venant des drivers/agents.
    """
    code = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text='Code stable ex: "ACCESS_GRANTED", "DOOR_FORCED".',
    )
    category = models.CharField(
        max_length=16, choices=EventCategory.choices, db_index=True,
    )
    label = models.CharField(
        max_length=140,
        help_text="Libellé affiché en français dans l'UI.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description détaillée pour tooltip / documentation.",
    )
    severity_default = models.CharField(
        max_length=12, choices=EventSeverity.choices,
        default=EventSeverity.INFO,
        help_text="Sévérité par défaut si l'événement ne la précise pas.",
    )
    result_default = models.CharField(
        max_length=12, choices=EventResult.choices,
        default=EventResult.NEUTRAL,
    )
    icon = models.CharField(
        max_length=40, blank=True,
        help_text='Nom lucide-react (ex: "shield-alert", "door-open").',
    )
    color = models.CharField(
        max_length=20, blank=True,
        help_text='Classe Tailwind ou hex — ex: "text-danger", "#f97316".',
    )
    # Alertes automatiques
    triggers_alert = models.BooleanField(
        default=False,
        help_text="Génère automatiquement une SystemAlert quand reçu.",
    )
    requires_ack = models.BooleanField(
        default=False,
        help_text="Requiert un acquittement humain (bouton dans l'UI).",
    )
    # Configuration
    is_active = models.BooleanField(
        default=True,
        help_text="False pour désactiver un type sans le supprimer.",
    )
    is_system = models.BooleanField(
        default=False,
        help_text="True pour les 69 types de base — protégés contre "
                    "suppression accidentelle.",
    )

    class Meta:
        ordering = ["category", "code"]
        verbose_name = "Type d'événement"
        verbose_name_plural = "Types d'événements"
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["severity_default"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.label})"


# ═══════════════════════════════════════════════════════════════════
# DeviceEvent — événement technique unifié
# ═══════════════════════════════════════════════════════════════════
class DeviceEvent(models.Model):
    """Événement technique remonté par un device, gateway, agent ou driver.

    Complète (pas remplace) AccessEvent de access_control :
      - AccessEvent = événement métier d'accès (badge scanné, autorisation)
      - DeviceEvent = événement technique (device online/offline, sync KO,
                       tamper, firmware update, agent crash, etc.)

    Pour un badge scanné qui déclenche un accès, on créera :
      1 AccessEvent (métier — décision granted/denied)
      + 1 DeviceEvent lié (technique — BADGE_DETECTED sur DEVICE X)

    Le modèle est optimisé pour la volumétrie (indexes multi-colonnes)
    et l'affichage temps réel (uuid + received_at + is_synced flag).
    """
    # ─── Identification ────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )
    event_type = models.ForeignKey(
        EventType, on_delete=models.PROTECT, related_name="events",
        db_index=True,
    )
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="device_events",
        db_index=True,
    )

    # ─── Localisation ──────────────────────────────────────────
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="device_events", db_index=True,
    )
    zone = models.ForeignKey(
        "sites.Zone", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="device_events",
    )
    checkpoint = models.ForeignKey(
        "sites.Checkpoint", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="device_events",
    )

    # ─── Sources techniques ────────────────────────────────────
    device = models.ForeignKey(
        "devices.Device", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tech_events", db_index=True,
    )
    gateway = models.ForeignKey(
        "devices.LocalAgent", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="events_via_gateway",
        help_text="Gateway Edge ayant relayé l'événement (peut différer du device).",
    )
    agent = models.ForeignKey(
        "devices.LocalAgent", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="events_local",
        help_text="Agent local (peut être un sous-agent RFID/BLE spécialisé).",
    )
    driver_code = models.CharField(
        max_length=40, blank=True,
        help_text='Ex: "hikvision", "zkteco", "onvif".',
    )

    # ─── Personne + badge/casque (si applicable) ───────────────
    holder_kind = models.CharField(
        max_length=12, blank=True,
        choices=[
            ("employee", "Employé"),
            ("worker",   "Ouvrier"),
            ("visitor",  "Visiteur"),
            ("agent",    "Agent"),
            ("vehicle",  "Véhicule"),
            ("unknown",  "Inconnu"),
        ],
    )
    holder_ref = models.CharField(
        max_length=64, blank=True,
        help_text='ID textuel de la personne — "EMP-1234" / "VIS-9".',
    )
    badge_uid = models.CharField(max_length=64, blank=True, db_index=True)
    helmet_uid = models.CharField(max_length=64, blank=True, db_index=True)

    # ─── Résultat + sévérité (peuvent surcharger les défauts EventType) ─
    result = models.CharField(
        max_length=12, choices=EventResult.choices,
        default=EventResult.NEUTRAL, db_index=True,
    )
    severity = models.CharField(
        max_length=12, choices=EventSeverity.choices,
        default=EventSeverity.INFO, db_index=True,
    )

    # ─── Timestamps ────────────────────────────────────────────
    occurred_at = models.DateTimeField(
        db_index=True,
        help_text="Timestamp d'origine (device ou driver).",
    )
    received_at = models.DateTimeField(
        auto_now_add=True, db_index=True,
        help_text="Timestamp de réception par le serveur cloud.",
    )

    # ─── Transmission ──────────────────────────────────────────
    transmission_mode = models.CharField(
        max_length=16, choices=TransmissionMode.choices,
        default=TransmissionMode.REALTIME_CLOUD, db_index=True,
    )
    is_offline = models.BooleanField(
        default=False, db_index=True,
        help_text="True si l'événement a été mis en queue offline avant transmission.",
    )
    is_synced = models.BooleanField(
        default=True, db_index=True,
        help_text="False si l'événement provient d'un batch de sync différée "
                    "et attend encore une confirmation cloud.",
    )
    sync_batch_id = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="ID du batch de synchronisation ayant remonté cet event.",
    )

    # ─── Payload technique brut ────────────────────────────────
    payload = models.JSONField(
        default=dict, blank=True,
        help_text="Payload driver brut — pour debug + réplay.",
    )
    message = models.TextField(
        blank=True,
        help_text="Résumé humain de l'événement — 1 ligne max.",
    )
    photo_url = models.URLField(
        blank=True,
        help_text="Snapshot MinIO/S3 si dispo (caméra, biométrique).",
    )

    # ─── Lien avec AccessEvent (métier accès) ──────────────────
    access_event = models.OneToOneField(
        "access_control.AccessEvent",
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tech_event",
        help_text="Si l'événement a déclenché une décision d'accès métier.",
    )

    # ─── Déduplication ─────────────────────────────────────────
    idempotency_key = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Hash unique pour dédupliquer les rejeus MQTT/WS.",
    )

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "Événement technique"
        verbose_name_plural = "Événements techniques"
        indexes = [
            # Filtres du cahier des charges section 1.2 :
            models.Index(fields=["tenant", "-occurred_at"]),
            models.Index(fields=["site", "-occurred_at"]),
            models.Index(fields=["event_type", "-occurred_at"]),
            models.Index(fields=["severity", "-occurred_at"]),
            models.Index(fields=["result", "-occurred_at"]),
            models.Index(fields=["gateway", "-occurred_at"]),
            models.Index(fields=["device", "-occurred_at"]),
            models.Index(fields=["is_offline", "-occurred_at"]),
            models.Index(fields=["is_synced", "-occurred_at"]),
            models.Index(fields=["transmission_mode", "-occurred_at"]),
        ]
        constraints = [
            # Déduplication forte quand la clé est fournie
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="devevent_idempotency_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M} · {self.event_type.code}"


# ═══════════════════════════════════════════════════════════════════
# EventAcknowledgement — traçabilité acquittements + résolutions
# ═══════════════════════════════════════════════════════════════════
class EventAcknowledgement(models.Model):
    """Historique immuable des acquittements/résolutions d'événements.

    Cahier des charges section 1.6 :
      - acquitter une alerte
      - marquer comme traité
      - créer un incident
      - ajouter un commentaire
      - joindre une preuve

    Un même événement peut avoir plusieurs actions successives (ex: ack
    puis resolve après investigation). L'objet est append-only — pas
    d'update ni de delete depuis l'API.
    """
    ACTION_CHOICES = [
        ("acknowledge", "Acquittement"),
        ("resolve",     "Résolution"),
        ("escalate",    "Escalade"),
        ("comment",     "Commentaire"),
        ("evidence",    "Preuve jointe"),
        ("reopen",      "Réouverture"),
    ]

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )
    event = models.ForeignKey(
        DeviceEvent, on_delete=models.CASCADE,
        related_name="acknowledgements",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT, related_name="event_acks",
    )
    notes = models.TextField(blank=True)
    evidence_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Acquittement d'événement"
        indexes = [
            models.Index(fields=["event", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.user} · {self.created_at:%Y-%m-%d %H:%M}"
