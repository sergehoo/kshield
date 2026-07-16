"""KAYDAN SHIELD — Modèles Edge Sync (Phase 4 refonte cahier §4.5).

Objectif : synchroniser Edge Gateway ↔ Cloud avec :
  - batches idempotents (checksums SHA256)
  - reprise après coupure réseau
  - priorité pour events critiques
  - détection + résolution de conflits
  - journal complet pour audit

Modèles :
  - EdgeSyncBatch : un batch entier de sync (gateway → cloud ou inverse)
  - EdgeSyncItem : un item individuel d'un batch (event, badge, config, ...)
  - EdgeSyncConflict : conflit détecté (même entité modifiée des 2 côtés)

Un batch peut contenir plusieurs types d'objets simultanément (events
+ badges revoked + config updates). Chaque item est identifié par
(entity_type, entity_id) pour la déduplication.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from core.mixins import TimeStampedModel


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════
class SyncDirection(models.TextChoices):
    """Sens du batch."""
    UPLOAD   = "upload",   "Edge → Cloud (upload)"
    DOWNLOAD = "download", "Cloud → Edge (download)"


class SyncStatus(models.TextChoices):
    """État du batch — machine à états simple."""
    PENDING     = "pending",     "En attente"
    UPLOADING   = "uploading",   "Upload en cours"
    PROCESSING  = "processing",  "Traitement serveur"
    COMPLETED   = "completed",   "Complété"
    PARTIAL     = "partial",     "Partiel (avec erreurs)"
    FAILED      = "failed",      "Échec définitif"
    CANCELLED   = "cancelled",   "Annulé"


class SyncPriority(models.TextChoices):
    """Priorité — les batches CRITICAL passent avant NORMAL."""
    LOW      = "low",      "Basse (config, catalogues)"
    NORMAL   = "normal",   "Normale (events routiniers)"
    HIGH     = "high",     "Haute (badges révoqués)"
    CRITICAL = "critical", "Critique (alertes, fraudes)"


class SyncEntityType(models.TextChoices):
    """Types d'entités synchronisables (aligné avec cahier §4.5)."""
    EVENT              = "event",              "Événement technique"
    ACCESS_EVENT       = "access_event",       "Événement d'accès"
    ALERT              = "alert",              "Alerte système"
    BADGE              = "badge",              "Badge"
    BADGE_ASSIGNMENT   = "badge_assignment",   "Attribution de badge"
    BADGE_REVOCATION   = "badge_revocation",   "Révocation de badge"
    HELMET             = "helmet",             "Casque BLE"
    EMPLOYEE           = "employee",           "Employé"
    WORKER             = "worker",             "Ouvrier"
    VISITOR            = "visitor",            "Visiteur"
    ACCESS_RULE        = "access_rule",        "Règle d'accès"
    SITE               = "site",               "Site"
    ZONE               = "zone",               "Zone"
    CHECKPOINT         = "checkpoint",         "Point d'accès"
    DEVICE             = "device",             "Équipement"
    DEVICE_CONFIG      = "device_config",      "Config équipement"
    OFFLINE_LOG        = "offline_log",        "Journal offline"


class ConflictResolution(models.TextChoices):
    """Stratégies de résolution des conflits."""
    PENDING       = "pending",       "En attente de résolution"
    CLOUD_WINS    = "cloud_wins",    "Cloud a raison (écrase local)"
    EDGE_WINS     = "edge_wins",     "Edge a raison (écrase cloud)"
    MERGE         = "merge",         "Fusion manuelle appliquée"
    IGNORE        = "ignore",        "Conflit ignoré (accepté tel quel)"
    ESCALATED     = "escalated",     "Escaladé à admin humain"


# ═══════════════════════════════════════════════════════════════════
# EdgeSyncBatch — orchestration d'un batch de sync
# ═══════════════════════════════════════════════════════════════════
class EdgeSyncBatch(TimeStampedModel):
    """Un batch = une transaction de synchronisation atomique.

    Un agent peut avoir plusieurs batches en cours simultanément
    (upload events + download config), mais chaque batch est atomique :
    on ne considère le contenu appliqué que si status == COMPLETED.

    Idempotence : ``batch_id`` fourni par l'agent Go — un même batch_id
    ne peut jamais être traité 2 fois même en cas de retry après crash.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Identifiant client (généré par l'agent Go) — unique par gateway
    batch_id = models.CharField(
        max_length=64, db_index=True,
        help_text="ID généré par l'agent (ex: uuid+timestamp).",
    )

    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="sync_batches",
    )
    gateway = models.ForeignKey(
        "devices.LocalAgent", on_delete=models.CASCADE, related_name="sync_batches",
        db_index=True,
    )

    direction = models.CharField(
        max_length=10, choices=SyncDirection.choices, db_index=True,
    )
    status = models.CharField(
        max_length=16, choices=SyncStatus.choices, default=SyncStatus.PENDING,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10, choices=SyncPriority.choices, default=SyncPriority.NORMAL,
        db_index=True,
    )

    # ─── Compteurs ─────────────────────────────────────────────
    items_declared = models.PositiveIntegerField(
        default=0, help_text="Nombre d'items annoncés par l'agent au start.",
    )
    items_uploaded = models.PositiveIntegerField(default=0)
    items_processed = models.PositiveIntegerField(default=0)
    items_succeeded = models.PositiveIntegerField(default=0)
    items_failed    = models.PositiveIntegerField(default=0)
    items_conflicted = models.PositiveIntegerField(default=0)

    # ─── Checksums pour détection corruption ───────────────────
    checksum_algorithm = models.CharField(
        max_length=16, default="sha256",
        help_text="Algo utilisé (sha256 obligatoire, blake3 pour perf).",
    )
    checksum_declared = models.CharField(
        max_length=128, blank=True,
        help_text="Hash annoncé par l'agent au start (checksum de tout le batch).",
    )
    checksum_computed = models.CharField(
        max_length=128, blank=True,
        help_text="Hash recalculé côté serveur après réception complète.",
    )

    # ─── Timings ───────────────────────────────────────────────
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    upload_finished_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    # ─── Reprise après interruption ─────────────────────────────
    resume_from_offset = models.PositiveIntegerField(
        default=0,
        help_text="Offset (en items) où reprendre après crash. 0 = début.",
    )
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    # ─── Compression + chiffrement ─────────────────────────────
    compression = models.CharField(
        max_length=16, blank=True,
        choices=[("", "Aucune"), ("gzip", "gzip"), ("zstd", "zstd")],
    )
    encryption = models.CharField(
        max_length=32, blank=True,
        help_text='Ex: "AES-256-GCM" — vide = TLS uniquement.',
    )

    # ─── Métadonnées ───────────────────────────────────────────
    payload_size_bytes = models.BigIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Batch de synchronisation Edge"
        indexes = [
            models.Index(fields=["gateway", "-started_at"]),
            models.Index(fields=["tenant", "status", "-started_at"]),
            models.Index(fields=["priority", "status"]),
            models.Index(fields=["direction", "status"]),
        ]
        constraints = [
            # Idempotence forte : un batch_id ne peut pas être créé 2x pour
            # la même gateway.
            models.UniqueConstraint(
                fields=["gateway", "batch_id"],
                name="edgesync_batch_id_unique_per_gw",
            ),
        ]

    def __str__(self) -> str:
        return (f"{self.direction[:2].upper()} {self.batch_id[:12]} "
                f"({self.status}, {self.items_succeeded}/{self.items_declared})")


# ═══════════════════════════════════════════════════════════════════
# EdgeSyncItem — un item individuel d'un batch
# ═══════════════════════════════════════════════════════════════════
class EdgeSyncItem(models.Model):
    """Un objet individuel dans un batch (event, badge, config, ...).

    On stocke l'ID origine + le payload JSON compressé si nécessaire.
    Un item peut être en erreur sans faire échouer tout le batch —
    on utilise status = ``failed`` sur l'item et le batch continue.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        EdgeSyncBatch, on_delete=models.CASCADE, related_name="items",
    )

    entity_type = models.CharField(
        max_length=32, choices=SyncEntityType.choices, db_index=True,
    )
    # Clé métier de l'entité (UUID ou ID textuel selon type)
    entity_key = models.CharField(
        max_length=128, db_index=True,
        help_text="Clé unique de l'entité côté Edge (ex: UUID event, uid badge).",
    )
    # Version édition pour détection conflits (compteur monotone Edge-side)
    entity_version = models.PositiveIntegerField(
        default=1,
        help_text="Version de l'entité côté Edge — permet détection conflit.",
    )

    # ─── Payload ───────────────────────────────────────────────
    payload = models.JSONField(default=dict, blank=True)
    payload_hash = models.CharField(
        max_length=64, blank=True,
        help_text="SHA256 du payload — pour dédup + intégrité.",
    )

    # ─── Statut ────────────────────────────────────────────────
    STATUS_CHOICES = [
        ("pending",   "En attente"),
        ("succeeded", "Traité avec succès"),
        ("failed",    "Erreur"),
        ("conflict",  "Conflit détecté"),
        ("skipped",   "Ignoré (dédup)"),
    ]
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="pending", db_index=True,
    )
    error = models.TextField(blank=True)

    # ─── Timings ───────────────────────────────────────────────
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    # ─── Lien vers l'objet créé côté cloud (si applicable) ─────
    resolved_object_id = models.CharField(
        max_length=64, blank=True,
        help_text="PK cloud de l'objet créé/modifié suite à ce sync.",
    )

    class Meta:
        ordering = ["batch", "received_at"]
        verbose_name = "Item de synchronisation"
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["entity_type", "entity_key"]),
            models.Index(fields=["payload_hash"]),
        ]
        constraints = [
            # Un même batch ne peut pas contenir 2 items pour la même
            # (entity_type, entity_key) — évite les doublons intra-batch.
            models.UniqueConstraint(
                fields=["batch", "entity_type", "entity_key"],
                name="edgesync_item_dedup_per_batch",
            ),
        ]


# ═══════════════════════════════════════════════════════════════════
# EdgeSyncConflict — conflit détecté à résoudre
# ═══════════════════════════════════════════════════════════════════
class EdgeSyncConflict(TimeStampedModel):
    """Conflit détecté lors d'un merge (même entité modifiée des 2 côtés).

    Exemple : le cloud a désactivé le badge X à 14h30, l'Edge (offline
    depuis 14h) a enregistré un check-in avec le même badge à 14h45.
    Au reconnect, le cloud reçoit le check-in mais le badge est
    disabled → conflit → décision : ignore, admin escalation, etc.

    Un conflit reste ``pending`` jusqu'à décision humaine (ou règle auto
    du cahier des charges §4.5).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        EdgeSyncBatch, on_delete=models.CASCADE, related_name="conflicts",
    )
    item = models.ForeignKey(
        EdgeSyncItem, on_delete=models.CASCADE, related_name="conflicts",
    )
    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE, related_name="sync_conflicts",
    )

    entity_type = models.CharField(max_length=32, db_index=True)
    entity_key = models.CharField(max_length=128, db_index=True)

    # Snapshots des versions en conflit
    edge_payload = models.JSONField(default=dict, blank=True)
    cloud_payload = models.JSONField(default=dict, blank=True)
    edge_version = models.PositiveIntegerField(default=0)
    cloud_version = models.PositiveIntegerField(default=0)
    edge_updated_at = models.DateTimeField(null=True, blank=True)
    cloud_updated_at = models.DateTimeField(null=True, blank=True)

    # Résolution
    resolution = models.CharField(
        max_length=16, choices=ConflictResolution.choices,
        default=ConflictResolution.PENDING, db_index=True,
    )
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sync_conflicts_resolved",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Conflit de synchronisation"
        indexes = [
            models.Index(fields=["resolution", "-created_at"]),
            models.Index(fields=["entity_type", "entity_key"]),
            models.Index(fields=["tenant", "resolution"]),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}/{self.entity_key} · {self.resolution}"
