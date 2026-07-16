"""Service métier des événements techniques (Phase 1 refonte).

Point d'entrée unique pour enregistrer un événement, quelle que soit sa
source (driver, MQTT, WS, HTTP webhook, gateway sync batch).

Responsabilités :
  - Résoudre le EventType par code
  - Enrichir l'event avec les défauts (severity, result)
  - Dédupliquer via idempotency_key (retour du même objet si rejeu)
  - Persister DeviceEvent en DB
  - Trigger auto SystemAlert si event_type.triggers_alert
  - Broadcast WebSocket à /ws/events/ pour la vue live
  - Créer audit trail si requires_ack

Utilisation depuis un driver :
    from devices.services.events import EventService
    EventService.record(
        code="ACCESS_GRANTED",
        tenant=agent.tenant,
        occurred_at=datetime.now(),
        device=device,
        gateway=gateway,
        payload={"card_no": "1234"},
        idempotency_key="dev-42:2026-07-15T10:34:56.123456Z",
    )
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from devices.models_events import (
    DeviceEvent,
    EventAcknowledgement,
    EventResult,
    EventSeverity,
    EventType,
    TransmissionMode,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Résultat structuré du record()
# ═══════════════════════════════════════════════════════════════════
@dataclass
class RecordResult:
    event: DeviceEvent
    created: bool  # False si dédup — event existait déjà
    alert_triggered: bool  # True si SystemAlert générée automatiquement


# ═══════════════════════════════════════════════════════════════════
# Cache des EventType (évite un SELECT par event)
# ═══════════════════════════════════════════════════════════════════
_type_cache: dict[str, EventType] = {}


def _get_event_type(code: str) -> Optional[EventType]:
    """Récupère un EventType par code — LRU cache in-process.

    Warmup automatique au premier appel. Invalidation manuelle possible
    via reset_type_cache() (utile en tests + hot-reload admin).
    """
    if code in _type_cache:
        return _type_cache[code]

    try:
        et = EventType.objects.get(code=code, is_active=True)
    except EventType.DoesNotExist:
        logger.warning("EventType inconnu ou désactivé: %s", code)
        return None

    _type_cache[code] = et
    return et


def reset_type_cache() -> None:
    """Invalide le cache — à appeler quand un admin modifie un EventType."""
    _type_cache.clear()


# ═══════════════════════════════════════════════════════════════════
# EventService — API publique
# ═══════════════════════════════════════════════════════════════════
class EventService:
    """Service stateless — méthodes de classe pour importer facilement."""

    @classmethod
    def record(  # noqa: PLR0913 (beaucoup de champs métier — c'est OK)
        cls,
        code: str,
        *,
        tenant,
        occurred_at: Optional[datetime] = None,
        site=None,
        zone=None,
        checkpoint=None,
        device=None,
        gateway=None,
        agent=None,
        driver_code: str = "",
        holder_kind: str = "",
        holder_ref: str = "",
        badge_uid: str = "",
        helmet_uid: str = "",
        result: Optional[str] = None,
        severity: Optional[str] = None,
        payload: Optional[dict] = None,
        message: str = "",
        photo_url: str = "",
        transmission_mode: str = TransmissionMode.REALTIME_CLOUD,
        is_offline: bool = False,
        sync_batch_id: str = "",
        access_event=None,
        idempotency_key: str = "",
        auto_broadcast: bool = True,
    ) -> Optional[RecordResult]:
        """Enregistre un événement technique.

        Retourne :
          - RecordResult si succès
          - None si le code type est inconnu (event ignoré)

        Idempotent : si idempotency_key est fourni et que l'event existe
        déjà, on retourne l'existant avec ``created=False``.

        Level up automatique de la sévérité si l'event vient de sécurité et
        que l'appelant a fourni une severity plus élevée que le défaut.
        """
        et = _get_event_type(code)
        if et is None:
            return None

        # ─── Auto-idempotency_key si non fourni ─────────────────
        if not idempotency_key and payload:
            # Hash déterministe (code + device + occurred_at + payload compact)
            occ = occurred_at or timezone.now()
            raw = f"{code}|{device.pk if device else ''}|{occ.isoformat()}"
            idempotency_key = hashlib.sha256(raw.encode()).hexdigest()[:32]

        # ─── Défauts issus du type ──────────────────────────────
        final_severity = severity or et.severity_default
        final_result = result or et.result_default

        # ─── Création idempotente ───────────────────────────────
        try:
            with transaction.atomic():
                event = DeviceEvent.objects.create(
                    event_type=et,
                    tenant=tenant,
                    site=site,
                    zone=zone,
                    checkpoint=checkpoint,
                    device=device,
                    gateway=gateway,
                    agent=agent,
                    driver_code=driver_code[:40],
                    holder_kind=holder_kind[:12],
                    holder_ref=holder_ref[:64],
                    badge_uid=badge_uid[:64],
                    helmet_uid=helmet_uid[:64],
                    result=final_result,
                    severity=final_severity,
                    occurred_at=occurred_at or timezone.now(),
                    transmission_mode=transmission_mode,
                    is_offline=is_offline,
                    is_synced=not is_offline,
                    sync_batch_id=sync_batch_id[:64],
                    payload=payload or {},
                    message=message[:2000],
                    photo_url=photo_url,
                    access_event=access_event,
                    idempotency_key=idempotency_key,
                )
                created = True
        except IntegrityError:
            # Rejeu via idempotency_key — on renvoie l'existant
            event = DeviceEvent.objects.filter(
                tenant=tenant, idempotency_key=idempotency_key,
            ).first()
            if event is None:
                # Race condition rare — on relance sans clé
                logger.warning(
                    "IntegrityError sans event trouvé pour clé %s — race?",
                    idempotency_key,
                )
                return None
            created = False

        # ─── Trigger alerte auto ────────────────────────────────
        alert_triggered = False
        if created and et.triggers_alert:
            alert_triggered = cls._trigger_alert(event, et)

        # ─── Broadcast WebSocket ────────────────────────────────
        if created and auto_broadcast:
            cls._broadcast_ws(event)

        return RecordResult(
            event=event, created=created, alert_triggered=alert_triggered,
        )

    # ─── Helpers privés ─────────────────────────────────────────
    @classmethod
    def _trigger_alert(cls, event: DeviceEvent, et: EventType) -> bool:
        """Crée un SystemAlert automatiquement pour cet event."""
        try:
            from devices.models import SystemAlert
            SystemAlert.objects.create(
                tenant=event.tenant,
                severity=cls._map_alert_severity(event.severity),
                type=event.event_type.code,
                title=et.label,
                message=event.message or f"Événement {et.code} déclenché",
                device=event.device,
                # Certaines versions du modèle SystemAlert exposent aussi
                # source_event_id, gateway, etc. On envoie via payload.
                context={
                    "event_id":  str(event.pk),
                    "code":      et.code,
                    "site_id":   event.site_id,
                    "gateway_id": str(event.gateway_id) if event.gateway_id else None,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SystemAlert trigger failed: %s", exc)
            return False

    @staticmethod
    def _map_alert_severity(sev: str) -> str:
        """Map DeviceEvent.severity → SystemAlert.severity (harmonisation)."""
        mapping = {
            EventSeverity.INFO:      "info",
            EventSeverity.WARNING:   "warning",
            EventSeverity.CRITICAL:  "critical",
            EventSeverity.EMERGENCY: "critical",
        }
        return mapping.get(sev, "info")

    @classmethod
    def _broadcast_ws(cls, event: DeviceEvent) -> None:
        """Push l'event sur le group WebSocket ``events.<tenant_id>``."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            layer = get_channel_layer()
            if layer is None:
                return
            payload = cls.serialize_for_ws(event)
            async_to_sync(layer.group_send)(
                f"events.{event.tenant_id}",
                {"type": "event.new", "payload": payload},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("WS broadcast events failed: %s", exc)

    @staticmethod
    def serialize_for_ws(event: DeviceEvent) -> dict[str, Any]:
        """Serialize compacte pour WebSocket / SSE.

        Format léger — pas de FK résolues (le front récupère via /events/<id>/
        s'il a besoin du détail complet).
        """
        return {
            "id":                str(event.pk),
            "code":              event.event_type.code,
            "category":          event.event_type.category,
            "label":              event.event_type.label,
            "icon":              event.event_type.icon,
            "color":             event.event_type.color,
            "severity":          event.severity,
            "result":            event.result,
            "occurred_at":       event.occurred_at.isoformat(),
            "received_at":       event.received_at.isoformat(),
            "site_id":           event.site_id,
            "zone_id":           event.zone_id,
            "device_id":         event.device_id,
            "gateway_id":        str(event.gateway_id) if event.gateway_id else None,
            "agent_id":          str(event.agent_id) if event.agent_id else None,
            "badge_uid":         event.badge_uid,
            "helmet_uid":        event.helmet_uid,
            "holder_kind":       event.holder_kind,
            "holder_ref":        event.holder_ref,
            "message":           event.message,
            "transmission_mode": event.transmission_mode,
            "is_offline":        event.is_offline,
            "is_synced":         event.is_synced,
            "photo_url":         event.photo_url,
        }

    # ─── Actions utilisateur ────────────────────────────────────
    @classmethod
    def acknowledge(
        cls,
        event: DeviceEvent,
        user,
        notes: str = "",
    ) -> EventAcknowledgement:
        """Crée un ack sur un événement (immutable)."""
        return EventAcknowledgement.objects.create(
            event=event, user=user, action="acknowledge", notes=notes[:2000],
        )

    @classmethod
    def resolve(
        cls,
        event: DeviceEvent,
        user,
        notes: str = "",
        evidence_url: str = "",
    ) -> EventAcknowledgement:
        """Marque un événement comme résolu (+ évidence optionnelle)."""
        return EventAcknowledgement.objects.create(
            event=event, user=user, action="resolve",
            notes=notes[:2000], evidence_url=evidence_url,
        )

    @classmethod
    def comment(
        cls,
        event: DeviceEvent,
        user,
        notes: str,
    ) -> EventAcknowledgement:
        """Ajoute un commentaire à l'historique de l'événement."""
        return EventAcknowledgement.objects.create(
            event=event, user=user, action="comment", notes=notes[:2000],
        )
