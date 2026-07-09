"""KAYDAN SHIELD — bus d'événements temps réel.

Publie les événements sur les groupes Channels correspondants pour que :
  * le front WebSocket reçoive les scans/statuts en direct
  * les agents locaux reçoivent les commandes push

Événements broadcastés :
  rfid.card.detected, rfid.card.duplicate, rfid.card.enrolled, rfid.card.error
  device.connected, device.disconnected, device.status.updated
  device.command.completed, device.command.failed, device.timeout
  agent.connected, agent.disconnected

Chaque événement est envoyé à un ou plusieurs groupes Channels :
  - "enrollment.<session_id>"  → clients WS de cette session
  - "device.status"             → clients WS de la page statut globale
  - "agent.<agent_id>"          → agent local ciblé
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventBus:
    """Façade au-dessus de channels.layers.get_channel_layer().

    Les événements sont sérialisés en dict simple pour compatibilité JSON.
    Robuste à l'absence de channel layer (test/dev sync).
    """

    # ────── Sessions d'enrôlement ──────
    @staticmethod
    def emit_card_detected(session_id, uid: str, device_id=None,
                            device_serial: str = "", rssi: Optional[int] = None,
                            extra: Optional[dict] = None):
        EventBus._broadcast(f"enrollment.{session_id}", {
            "type": "session.event",
            "event": "rfid.card.detected",
            "session_id": str(session_id),
            "uid": uid,
            "device_id": device_id,
            "device_serial": device_serial,
            "rssi": rssi,
            "extra": extra or {},
            "at": _now_iso(),
        })

    @staticmethod
    def emit_card_duplicate(session_id, uid: str, existing_badge: Optional[dict] = None):
        EventBus._broadcast(f"enrollment.{session_id}", {
            "type": "session.event",
            "event": "rfid.card.duplicate",
            "session_id": str(session_id),
            "uid": uid,
            "existing_badge": existing_badge,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_card_enrolled(session_id, uid: str, badge: dict):
        EventBus._broadcast(f"enrollment.{session_id}", {
            "type": "session.event",
            "event": "rfid.card.enrolled",
            "session_id": str(session_id),
            "uid": uid,
            "badge": badge,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_card_error(session_id, uid: str, message: str):
        EventBus._broadcast(f"enrollment.{session_id}", {
            "type": "session.event",
            "event": "rfid.card.error",
            "session_id": str(session_id),
            "uid": uid,
            "message": message,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_session_status(session_id, status: str, message: str = "",
                             extra: Optional[dict] = None):
        EventBus._broadcast(f"enrollment.{session_id}", {
            "type": "session.event",
            "event": f"session.{status}",
            "session_id": str(session_id),
            "status": status,
            "message": message,
            "extra": extra or {},
            "at": _now_iso(),
        })

    # ────── Devices globaux ──────
    @staticmethod
    def emit_device_status(device_id, serial: str, status: str,
                            payload: Optional[dict] = None):
        EventBus._broadcast("device.status", {
            "type": "device.event",
            "event": "device.status.updated",
            "device_id": device_id,
            "serial": serial,
            "status": status,
            "payload": payload or {},
            "at": _now_iso(),
        })

    @staticmethod
    def emit_device_connected(device_id, serial: str):
        EventBus._broadcast("device.status", {
            "type": "device.event",
            "event": "device.connected",
            "device_id": device_id,
            "serial": serial,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_device_disconnected(device_id, serial: str):
        EventBus._broadcast("device.status", {
            "type": "device.event",
            "event": "device.disconnected",
            "device_id": device_id,
            "serial": serial,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_command_completed(command_id, device_id, kind: str, response: dict):
        EventBus._broadcast("device.status", {
            "type": "device.event",
            "event": "device.command.completed",
            "command_id": str(command_id),
            "device_id": device_id,
            "kind": kind,
            "response": response,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_command_failed(command_id, device_id, kind: str, error: str):
        EventBus._broadcast("device.status", {
            "type": "device.event",
            "event": "device.command.failed",
            "command_id": str(command_id),
            "device_id": device_id,
            "kind": kind,
            "error": error,
            "at": _now_iso(),
        })

    # ────── Agents locaux ──────
    @staticmethod
    def push_to_agent(agent_id, message: dict):
        """Push un message sur le canal WS d'un agent local."""
        EventBus._broadcast(f"agent.{agent_id}", {
            "type": "agent.message",
            **message,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_agent_connected(agent_id, label: str):
        EventBus._broadcast("device.status", {
            "type": "agent.event",
            "event": "agent.connected",
            "agent_id": str(agent_id),
            "label": label,
            "at": _now_iso(),
        })

    @staticmethod
    def emit_agent_disconnected(agent_id, label: str):
        EventBus._broadcast("device.status", {
            "type": "agent.event",
            "event": "agent.disconnected",
            "agent_id": str(agent_id),
            "label": label,
            "at": _now_iso(),
        })

    # ────── Internal ──────
    @staticmethod
    def _broadcast(group: str, payload: dict[str, Any]):
        """Broadcast synchrone au groupe Channels indiqué.

        On utilise ``async_to_sync`` pour être appelable depuis vues/tâches sync.
        Robuste : si le channel layer n'est pas dispo (tests), on log et on ignore.
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            layer = get_channel_layer()
            if layer is None:
                logger.debug("EventBus: pas de channel layer, event ignoré (%s)", group)
                return
            async_to_sync(layer.group_send)(group, payload)
        except Exception as exc:
            logger.exception("EventBus: erreur broadcast %s → %s", group, exc)
