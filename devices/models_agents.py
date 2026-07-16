"""KAYDAN SHIELD — Modèles Agents locaux (Phase 6 refonte §5).

Architecture :
  - LocalAgent (existant, modèle principal) : identité + tokens + WS
  - LocalAgentType (NEW) : catalogue des 10 types d'agents supportés
  - LocalAgentHeartbeat (NEW) : historique des métriques runtime
  - LocalAgentConfiguration (NEW) : configs versionnées immutables
  - LocalAgentLog (NEW) : buffer des logs pour supervision live

Les 9 états agents (cahier §5.3) sont exprimés via l'enum ``AgentState``.
"""
from __future__ import annotations

import uuid

from django.db import models

from core.mixins import TimeStampedModel


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════
class AgentState(models.TextChoices):
    """9 états explicites d'un agent local (cahier §5.3)."""
    INSTALLING  = "installing",  "Installation en cours"
    STARTING    = "starting",    "Démarrage"
    RUNNING     = "running",     "En cours d'exécution"
    DEGRADED    = "degraded",    "Dégradé (erreurs)"
    STOPPED     = "stopped",     "Arrêté"
    CRASHED     = "crashed",     "Crashé"
    UPDATING    = "updating",    "Mise à jour en cours"
    DISABLED    = "disabled",    "Désactivé (admin)"
    UNREACHABLE = "unreachable", "Injoignable"


class LogLevel(models.TextChoices):
    DEBUG    = "debug",    "Debug"
    INFO     = "info",     "Info"
    WARNING  = "warning",  "Warning"
    ERROR    = "error",    "Error"
    CRITICAL = "critical", "Critical"


# ═══════════════════════════════════════════════════════════════════
# LocalAgentType — catalogue des 10 types (cahier §5.1)
# ═══════════════════════════════════════════════════════════════════
class LocalAgentType(TimeStampedModel):
    """Catalogue des types d'agents disponibles.

    Peuplé par un seed initial (management command) puis administrable.
    Chaque type définit :
      - le module Go/Python qui l'implémente (module_name)
      - les capacités disponibles (list de codes)
      - les paramètres de configuration requis
    """
    TYPE_CODE_CHOICES = [
        ("rfid",         "Agent RFID (UHF / NFC)"),
        ("ble",          "Agent BLE (casques)"),
        ("camera",       "Agent Caméra (ONVIF / RTSP)"),
        ("biometric",    "Agent Biométrique"),
        ("attendance",   "Agent Terminal de pointage"),
        ("mqtt",         "Agent MQTT (broker relay)"),
        ("sync",         "Agent de synchronisation"),
        ("discovery",    "Agent de découverte réseau"),
        ("monitoring",   "Agent de monitoring"),
        ("generic",      "Agent constructeur générique"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=32, choices=TYPE_CODE_CHOICES, unique=True, db_index=True,
    )
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    module_name = models.CharField(
        max_length=120,
        help_text='Ex: "kshield_agent.agents.rfid" (Python) '
                    'ou "internal/agents/rfid" (Go).',
    )
    capabilities = models.JSONField(
        default=list, blank=True,
        help_text='Codes capacités ex: ["read_uid", "write_uid", "presence"].',
    )
    config_schema = models.JSONField(
        default=dict, blank=True,
        help_text="JSON Schema pour valider config à l'attribution.",
    )
    icon = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(
        default=False,
        help_text="True = type de base non supprimable.",
    )

    class Meta:
        ordering = ["code"]
        verbose_name = "Type d'agent local"

    def __str__(self) -> str:
        return f"{self.label} ({self.code})"


# ═══════════════════════════════════════════════════════════════════
# LocalAgentHeartbeat — historique des métriques (cahier §5.5)
# ═══════════════════════════════════════════════════════════════════
class LocalAgentHeartbeat(models.Model):
    """Historique des heartbeats envoyés par un agent.

    Chaque heartbeat contient les métriques runtime : CPU, mémoire,
    stockage, latence, taille file d'attente, dernières erreurs.

    Rétention typique : 7 jours (à configurer via task Celery beat).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        "devices.LocalAgent", on_delete=models.CASCADE,
        related_name="heartbeats",
    )
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE,
        related_name="agent_heartbeats",
    )

    # ─── Timestamps ────────────────────────────────────────────
    sent_at = models.DateTimeField(
        db_index=True,
        help_text="Timestamp de génération côté agent.",
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # ─── État agent ────────────────────────────────────────────
    state = models.CharField(
        max_length=16, choices=AgentState.choices,
        default=AgentState.RUNNING,
    )
    version = models.CharField(max_length=32, blank=True)
    uptime_seconds = models.BigIntegerField(default=0)

    # ─── Métriques système ─────────────────────────────────────
    cpu_percent = models.FloatField(default=0.0)
    memory_percent = models.FloatField(default=0.0)
    memory_mb = models.PositiveIntegerField(default=0)
    storage_percent = models.FloatField(default=0.0)
    storage_free_mb = models.PositiveIntegerField(default=0)
    network_latency_ms = models.PositiveIntegerField(default=0)

    # ─── Métriques métier ──────────────────────────────────────
    events_processed = models.BigIntegerField(default=0)
    events_pending = models.PositiveIntegerField(default=0)
    devices_connected = models.PositiveIntegerField(default=0)
    devices_expected = models.PositiveIntegerField(default=0)
    errors_last_hour = models.PositiveIntegerField(default=0)
    sync_last_success_at = models.DateTimeField(null=True, blank=True)

    # ─── Erreurs récentes (payload complet) ────────────────────
    recent_errors = models.JSONField(
        default=list, blank=True,
        help_text='Liste des N dernières erreurs (max 20 items).',
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Heartbeat d'agent"
        indexes = [
            models.Index(fields=["agent", "-sent_at"]),
            models.Index(fields=["tenant", "-received_at"]),
            models.Index(fields=["state", "-received_at"]),
        ]


# ═══════════════════════════════════════════════════════════════════
# LocalAgentConfiguration — configuration versionnée
# ═══════════════════════════════════════════════════════════════════
class LocalAgentConfiguration(TimeStampedModel):
    """Configuration d'un agent — versionnée et immutable une fois appliquée.

    Chaque modification crée une nouvelle version. L'agent applique la
    version courante (is_current=True) au boot ou sur commande admin.

    Format config : JSON libre — validé contre LocalAgentType.config_schema.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        "devices.LocalAgent", on_delete=models.CASCADE,
        related_name="configurations",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Compteur incrémental — auto-géré à chaque save.",
    )
    payload = models.JSONField(
        default=dict, blank=True,
        help_text="Config JSON complète (env, params vendor, timeouts, etc.)",
    )
    checksum = models.CharField(
        max_length=64, blank=True,
        help_text="SHA256 du payload pour dédup + intégrité.",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    is_current = models.BooleanField(
        default=False, db_index=True,
        help_text="True = version en cours d'usage par l'agent.",
    )
    is_draft = models.BooleanField(
        default=True,
        help_text="True = brouillon non-encore appliqué.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["agent", "-version"]
        verbose_name = "Configuration d'agent"
        indexes = [
            models.Index(fields=["agent", "-version"]),
            models.Index(fields=["agent", "is_current"]),
        ]
        constraints = [
            # 1 seule version courante par agent
            models.UniqueConstraint(
                fields=["agent"], condition=models.Q(is_current=True),
                name="agent_one_current_config",
            ),
        ]

    def __str__(self) -> str:
        state = "current" if self.is_current else \
                ("draft" if self.is_draft else "archived")
        return f"Config #{self.version} · {self.agent} · {state}"


# ═══════════════════════════════════════════════════════════════════
# LocalAgentLog — buffer de logs pour supervision live
# ═══════════════════════════════════════════════════════════════════
class LocalAgentLog(models.Model):
    """Logs bruts remontés par un agent pour supervision live.

    Rétention limitée (30 jours par défaut, purgeable). Pour l'audit
    complet + long terme, utiliser Loki/CloudWatch via l'agent Go
    directement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        "devices.LocalAgent", on_delete=models.CASCADE,
        related_name="logs",
    )
    ts = models.DateTimeField(db_index=True)
    level = models.CharField(
        max_length=8, choices=LogLevel.choices, default=LogLevel.INFO,
        db_index=True,
    )
    message = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    source = models.CharField(
        max_length=64, blank=True,
        help_text='Module/component source (ex: "mqtt.client", "driver.hikvision")',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ts"]
        verbose_name = "Log d'agent"
        indexes = [
            models.Index(fields=["agent", "-ts"]),
            models.Index(fields=["level", "-ts"]),
        ]
