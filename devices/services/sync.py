"""SyncService — Orchestration Edge Gateway ↔ Cloud (Phase 4).

Cahier des charges §4.5 :
  - synchronisation incrémentale ✓
  - batches ✓
  - reprise après interruption (resume_from_offset)
  - idempotence (unique batch_id + entity_key)
  - checksum SHA256 (blocs + total)
  - déduplication (payload_hash + unique constraint)
  - conflits (détection + résolution)
  - accusé de réception (status transitions)
  - priorité des événements critiques (priority CRITICAL first)
  - compression (gzip/zstd)
  - chiffrement (métadonnées, TLS obligatoire au transport)
  - journal (tous les batches persistés)

Flow typique upload Edge → Cloud :

    1. Agent Go   : sync.SyncService.start_batch(gateway, direction=upload,
                        items_declared=N, checksum_declared="...", priority)
    2. Agent Go   : sync.SyncService.add_items(batch, items[])
    3. Agent Go   : sync.SyncService.complete_batch(batch)
    4. Cloud      : traite items, détecte conflits, applique en DB
    5. Agent Go   : sync.SyncService.get_status(batch) → succeeded/partial/failed
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Structures publiques
# ═══════════════════════════════════════════════════════════════════
@dataclass
class SyncItem:
    """Un item de sync côté client (avant persistance)."""
    entity_type: str
    entity_key: str
    payload: dict
    entity_version: int = 1


@dataclass
class SyncResult:
    ok: bool
    batch: Any = None
    error: str = ""
    error_code: str = ""


# ═══════════════════════════════════════════════════════════════════
# SyncService — API publique
# ═══════════════════════════════════════════════════════════════════
class SyncService:
    """Service stateless — méthodes de classe."""

    CHUNK_SIZE = 500   # items max par sub-batch pour éviter OOM

    # ─── Lifecycle batch ────────────────────────────────────────
    @classmethod
    @transaction.atomic
    def start_batch(
        cls,
        gateway,
        batch_id: str,
        direction: str = "upload",
        items_declared: int = 0,
        priority: str = "normal",
        checksum_declared: str = "",
        compression: str = "",
        metadata: Optional[dict] = None,
    ) -> SyncResult:
        """Crée un nouveau batch. Idempotent — retourne l'existant si déjà créé."""
        from devices.models_sync import EdgeSyncBatch, SyncDirection, SyncPriority

        # Validation
        if direction not in dict(SyncDirection.choices):
            return SyncResult(ok=False, error_code="invalid_direction",
                               error=f"direction={direction} inconnue")
        if priority not in dict(SyncPriority.choices):
            return SyncResult(ok=False, error_code="invalid_priority",
                               error=f"priority={priority} inconnue")
        if not batch_id or len(batch_id) < 8:
            return SyncResult(ok=False, error_code="invalid_batch_id",
                               error="batch_id requis (min 8 chars)")

        # Idempotence — recherche batch existant
        existing = EdgeSyncBatch.objects.filter(
            gateway=gateway, batch_id=batch_id,
        ).first()
        if existing:
            logger.debug("Batch %s existe déjà (status=%s) — dedup",
                          batch_id[:12], existing.status)
            return SyncResult(ok=True, batch=existing)

        try:
            batch = EdgeSyncBatch.objects.create(
                tenant=gateway.tenant,
                gateway=gateway,
                batch_id=batch_id,
                direction=direction,
                priority=priority,
                items_declared=items_declared,
                checksum_declared=checksum_declared[:128],
                compression=compression[:16],
                metadata=metadata or {},
                status="uploading" if direction == "upload" else "processing",
            )
        except IntegrityError as e:
            return SyncResult(ok=False, error_code="db_error", error=str(e))

        logger.info("SyncBatch créé : %s (gw=%s, direction=%s, items_declared=%d)",
                     batch_id[:12], gateway.pk, direction, items_declared)
        return SyncResult(ok=True, batch=batch)

    @classmethod
    def add_items(
        cls,
        batch,
        items: list[SyncItem | dict],
    ) -> dict:
        """Ajoute des items au batch. Dédup par (batch, entity_type, entity_key).

        Retourne stats : {added, dedup, invalid}
        """
        from devices.models_sync import EdgeSyncItem

        # Normalize dicts → SyncItem
        normalized: list[SyncItem] = []
        invalid = 0
        for raw in items:
            if isinstance(raw, dict):
                try:
                    normalized.append(SyncItem(
                        entity_type=raw["entity_type"],
                        entity_key=str(raw["entity_key"]),
                        payload=raw.get("payload") or {},
                        entity_version=int(raw.get("entity_version") or 1),
                    ))
                except (KeyError, ValueError):
                    invalid += 1
            elif isinstance(raw, SyncItem):
                normalized.append(raw)
            else:
                invalid += 1

        added = 0
        dedup = 0

        # Bulk create avec ignore_conflicts pour dédup silencieuse
        to_create = []
        for si in normalized:
            payload_str = json.dumps(si.payload, sort_keys=True, ensure_ascii=False)
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
            to_create.append(EdgeSyncItem(
                batch=batch,
                entity_type=si.entity_type[:32],
                entity_key=si.entity_key[:128],
                entity_version=si.entity_version,
                payload=si.payload,
                payload_hash=payload_hash,
                status="pending",
            ))

        if to_create:
            created = EdgeSyncItem.objects.bulk_create(
                to_create, ignore_conflicts=True,
            )
            # bulk_create ne renvoie pas les PKs sur toutes les DB — on
            # recompte via count après.
            added = EdgeSyncItem.objects.filter(batch=batch).count() - \
                    batch.items_uploaded
            dedup = len(to_create) - added

        # Update counters
        batch.items_uploaded += added
        batch.save(update_fields=["items_uploaded"])

        return {"added": added, "dedup": dedup, "invalid": invalid}

    @classmethod
    @transaction.atomic
    def complete_batch(
        cls,
        batch,
        checksum_computed: str = "",
    ) -> SyncResult:
        """Finalise un batch upload : vérifie checksum + traite les items."""
        from devices.models_sync import EdgeSyncItem, EdgeSyncBatch

        # Vérif checksum si fourni
        if batch.checksum_declared and checksum_computed and \
                batch.checksum_declared != checksum_computed:
            batch.status = "failed"
            batch.last_error = (f"Checksum mismatch : "
                                 f"declared={batch.checksum_declared[:16]}... "
                                 f"computed={checksum_computed[:16]}...")
            batch.save(update_fields=["status", "last_error"])
            return SyncResult(ok=False, batch=batch,
                                error_code="checksum_mismatch",
                                error=batch.last_error)

        batch.checksum_computed = checksum_computed[:128]
        batch.upload_finished_at = timezone.now()
        batch.status = "processing"
        batch.save(update_fields=[
            "checksum_computed", "upload_finished_at", "status",
        ])

        # Traite chaque item par ordre reçu
        stats = cls._process_items(batch)

        # Détermine status final
        if stats["failed"] == 0 and stats["conflict"] == 0:
            batch.status = "completed"
        elif stats["succeeded"] > 0:
            batch.status = "partial"
        else:
            batch.status = "failed"

        batch.items_processed = sum(stats.values())
        batch.items_succeeded = stats["succeeded"]
        batch.items_failed = stats["failed"]
        batch.items_conflicted = stats["conflict"]
        batch.processed_at = timezone.now()
        # Duration
        if batch.started_at:
            batch.duration_ms = int(
                (batch.processed_at - batch.started_at).total_seconds() * 1000,
            )
        batch.save(update_fields=[
            "status", "items_processed", "items_succeeded",
            "items_failed", "items_conflicted", "processed_at", "duration_ms",
        ])
        logger.info("Batch %s complété : %s (succ=%d, fail=%d, cnf=%d)",
                     batch.batch_id[:12], batch.status,
                     stats["succeeded"], stats["failed"], stats["conflict"])
        return SyncResult(ok=batch.status != "failed", batch=batch)

    @classmethod
    def cancel_batch(cls, batch, reason: str = "") -> SyncResult:
        batch.status = "cancelled"
        batch.last_error = reason[:2000]
        batch.processed_at = timezone.now()
        batch.save(update_fields=["status", "last_error", "processed_at"])
        return SyncResult(ok=True, batch=batch)

    # ─── Traitement + détection conflits ─────────────────────────
    @classmethod
    def _process_items(cls, batch) -> dict[str, int]:
        """Traite tous les items pending d'un batch. Détecte conflits.

        Pour l'instant, seul le stockage est effectif — l'application aux
        modèles cibles (Badge, DeviceEvent, ...) est déléguée aux dispatchers
        métier via des signals ou tasks Celery.

        Retourne compteurs par statut.
        """
        from devices.models_sync import EdgeSyncItem

        stats = {"succeeded": 0, "failed": 0, "conflict": 0, "skipped": 0}
        items = EdgeSyncItem.objects.filter(batch=batch, status="pending")

        for item in items.iterator(chunk_size=200):
            try:
                # Dédup par payload_hash — si même hash existe déjà en cloud,
                # on marque skipped (idempotence).
                if item.payload_hash and cls._is_duplicate_payload(item):
                    item.status = "skipped"
                    item.processed_at = timezone.now()
                    item.save(update_fields=["status", "processed_at"])
                    stats["skipped"] += 1
                    continue

                # Détection conflit — même entité + version cloud > version edge
                conflict = cls._detect_conflict(item)
                if conflict is not None:
                    item.status = "conflict"
                    item.processed_at = timezone.now()
                    item.save(update_fields=["status", "processed_at"])
                    cls._record_conflict(batch, item, conflict)
                    stats["conflict"] += 1
                    continue

                # Application au modèle cible
                cls._apply_item(item)
                item.status = "succeeded"
                item.processed_at = timezone.now()
                item.save(update_fields=[
                    "status", "processed_at", "resolved_object_id",
                ])
                stats["succeeded"] += 1
            except Exception as e:  # noqa: BLE001
                item.status = "failed"
                item.error = str(e)[:2000]
                item.processed_at = timezone.now()
                item.save(update_fields=["status", "error", "processed_at"])
                stats["failed"] += 1
                logger.warning("Sync item %s failed: %s", item.pk, e)

        return stats

    @staticmethod
    def _is_duplicate_payload(item) -> bool:
        """Retourne True si un autre item ``succeeded`` a le même payload_hash
        pour la même entity_type/entity_key — un rejeu."""
        from devices.models_sync import EdgeSyncItem
        return EdgeSyncItem.objects.filter(
            entity_type=item.entity_type,
            entity_key=item.entity_key,
            payload_hash=item.payload_hash,
            status="succeeded",
        ).exclude(pk=item.pk).exists()

    @classmethod
    def _detect_conflict(cls, item):
        """Détecte un conflit d'écriture concurrente.

        Règle simplifiée MVP : conflit si l'entity_key existe déjà et
        item.entity_version < version_cloud (aucune version connue = 0).
        À enrichir avec règles spécifiques par entity_type dans un dispatcher.
        """
        # TODO Phase 4.5 : dispatcher métier par entity_type
        return None   # pas de conflit détecté pour l'instant

    @staticmethod
    def _record_conflict(batch, item, cloud_snapshot: dict):
        """Persiste un EdgeSyncConflict pour résolution ultérieure."""
        from devices.models_sync import EdgeSyncConflict
        EdgeSyncConflict.objects.create(
            batch=batch,
            item=item,
            tenant=batch.tenant,
            entity_type=item.entity_type,
            entity_key=item.entity_key,
            edge_payload=item.payload,
            cloud_payload=cloud_snapshot or {},
            edge_version=item.entity_version,
            cloud_version=cloud_snapshot.get("version", 0) if cloud_snapshot else 0,
        )

    @classmethod
    def _apply_item(cls, item) -> None:
        """Applique un item aux modèles Django cibles.

        Dispatcher par ``entity_type`` — pour l'instant on gère uniquement
        les events (déjà couverts par EventService.record côté agent).
        Les autres types (badges, config) seront ajoutés en 4.5+.
        """
        from devices.models_sync import SyncEntityType

        et = item.entity_type

        if et in (SyncEntityType.EVENT, SyncEntityType.ACCESS_EVENT):
            # Les events sont déjà appliqués via l'endpoint /agent/events/
            # côté agent — ici on marque juste comme succeeded sans re-créer.
            # L'entity_key contient l'UUID DeviceEvent.
            item.resolved_object_id = item.entity_key
            return

        if et == SyncEntityType.BADGE_REVOCATION:
            # Traité par Badge lifecycle service
            # TODO : appeler BadgeAssignmentService.revoke() ici
            return

        # Autres types : à implémenter selon priorité métier
        logger.debug("Sync item type '%s' non applicable côté cloud "
                      "— stockage brut uniquement", et)

    # ─── Résolution conflits ─────────────────────────────────────
    @classmethod
    @transaction.atomic
    def resolve_conflict(
        cls,
        conflict,
        resolution: str,
        user=None,
        notes: str = "",
    ) -> SyncResult:
        """Applique la décision de résolution d'un conflit."""
        from devices.models_sync import ConflictResolution

        if resolution not in dict(ConflictResolution.choices):
            return SyncResult(ok=False, error_code="invalid_resolution",
                                error=f"resolution={resolution} inconnue")

        if conflict.resolution != "pending":
            return SyncResult(ok=False, error_code="already_resolved",
                                error=f"Déjà résolu : {conflict.resolution}")

        conflict.resolution = resolution
        conflict.resolution_notes = notes[:2000]
        conflict.resolved_at = timezone.now()
        conflict.resolved_by = user
        conflict.save(update_fields=[
            "resolution", "resolution_notes", "resolved_at", "resolved_by",
        ])

        logger.info("Conflit %s résolu : %s par %s",
                     conflict.pk, resolution, user)
        return SyncResult(ok=True)

    # ─── Requêtes lecture ────────────────────────────────────────
    @classmethod
    def list_batches_for_gateway(cls, gateway, limit: int = 50):
        from devices.models_sync import EdgeSyncBatch
        return list(EdgeSyncBatch.objects.filter(
            gateway=gateway,
        ).order_by("-started_at")[:limit])

    @classmethod
    def get_pending_conflicts(cls, tenant, limit: int = 100):
        from devices.models_sync import EdgeSyncConflict
        return list(EdgeSyncConflict.objects.filter(
            tenant=tenant, resolution="pending",
        ).select_related("batch", "item", "batch__gateway")
         .order_by("-created_at")[:limit])
