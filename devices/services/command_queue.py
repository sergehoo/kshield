"""KAYDAN SHIELD — file de commandes device (serveur → équipement).

Trois modes de livraison selon l'équipement cible :

1. **Agent local via WebSocket** (préféré si l'agent est connecté)
   → push instantané sur ``agent.<agent_id>`` channel

2. **Terminal ADMS pull** (ZKTeco/AiFace)
   → dépôt en cache Redis clé ``iclock_cmd:<SN>``, lue au prochain heartbeat

3. **HTTP direct** (lecteur RFID avec API REST)
   → thread pool best-effort (POST vers l'IP du device)

Cycle de vie DB : pending → sent → acknowledged → completed | failed | timeout
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Clés Redis
CMD_QUEUE_KEY = "device_cmd_queue:{device_id}"     # liste des commandes en attente
CMD_STATE_KEY = "device_cmd_state:{command_id}"    # état intermédiaire d'une commande
ADMS_CMD_KEY  = "iclock_cmd:{serial}"              # legacy — commande ADMS pull-mode

CMD_TTL_SECONDS = 300   # commandes non consommées après 5min → expirées côté Redis
DEFAULT_TIMEOUT_SECONDS = 30


class DeviceCommandQueue:
    """Façade unique pour émettre des commandes vers un équipement.

    Exemple :
        cmd = DeviceCommandQueue.enqueue(
            device=my_reader,
            kind="START_RFID_ENROLLMENT",
            payload={"session_id": str(session.pk), "timeout": 180},
            issued_by=request.user,
            session=session,
        )
        # → cmd.pk disponible pour polling REST ou WebSocket
    """

    # ────────────────────────────────────────────────────────────
    # Émission
    # ────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def enqueue(*, device, kind: str, payload: Optional[dict] = None,
                 issued_by=None, session=None,
                 timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        """Persiste + dispatche une commande vers l'équipement.

        Retourne l'instance DeviceCommand (persistée, status "sent" si livraison OK,
        "pending" si aucun canal disponible).
        """
        from devices.models import DeviceCommand

        payload = payload or {}
        cmd = DeviceCommand.objects.create(
            tenant=device.tenant,
            device=device,
            session=session,
            kind=kind,
            payload=payload,
            issued_by=issued_by,
            status="pending",
            timeout_at=timezone.now() + timedelta(seconds=timeout_seconds),
        )

        delivered = DeviceCommandQueue._dispatch(cmd)
        if delivered:
            cmd.status = "sent"
            cmd.sent_at = timezone.now()
            cmd.save(update_fields=["status", "sent_at"])

        try:
            from core.metrics import device_commands_total
            device_commands_total.labels(kind=kind, status=cmd.status).inc()
        except Exception:
            pass

        logger.info(
            "DeviceCommand %s → device=%s kind=%s delivered=%s",
            cmd.pk, device.serial_number, kind, delivered,
        )
        return cmd

    # ────────────────────────────────────────────────────────────
    # Dispatch — choix du canal
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _dispatch(cmd) -> bool:
        """Tente la livraison via le meilleur canal disponible.

        Retourne True si un canal a accepté la commande, False sinon (elle reste
        en "pending" — un scheduler ou un heartbeat futur pourra la reprendre).
        """
        device = cmd.device
        payload_full = {
            "command_id": str(cmd.pk),
            "kind": cmd.kind,
            "payload": cmd.payload or {},
            "device_id": device.pk,
            "device_serial": device.serial_number,
        }

        # 1) Agent local connecté ?
        agent = DeviceCommandQueue._resolve_agent(device)
        if agent and agent.connected:
            from .event_bus import EventBus
            EventBus.push_to_agent(agent.pk, {"command": payload_full})
            # On stocke aussi en Redis pour rejeu si l'agent se déconnecte
            _push_redis_queue(device.pk, payload_full)
            return True

        # 2) Terminal ADMS (ZKTeco/AiFace) — pull mode
        if _is_adms_device(device):
            _set_adms_command(device, cmd.kind, cmd.payload or {})
            return True

        # 3) HTTP direct — best-effort en tâche de fond
        if device.ip_address:
            try:
                _try_http_direct(device, payload_full)
                return True
            except Exception as exc:
                logger.warning("HTTP direct KO pour %s: %s", device.serial_number, exc)

        # 4) Aucun canal — la commande reste "pending"
        return False

    # ────────────────────────────────────────────────────────────
    # Acknowledgement + résultat
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def acknowledge(command_id):
        """Marque la commande comme acquittée par l'équipement."""
        from devices.models import DeviceCommand
        try:
            cmd = DeviceCommand.objects.get(pk=command_id)
        except DeviceCommand.DoesNotExist:
            return None
        cmd.status = "acknowledged"
        cmd.acked_at = timezone.now()
        cmd.save(update_fields=["status", "acked_at"])
        return cmd

    @staticmethod
    def complete(command_id, response_raw: Optional[dict] = None,
                  response_normalized: Optional[dict] = None):
        from devices.models import DeviceCommand
        try:
            cmd = DeviceCommand.objects.get(pk=command_id)
        except DeviceCommand.DoesNotExist:
            return None
        cmd.status = "completed"
        cmd.completed_at = timezone.now()
        cmd.response_raw = response_raw or {}
        cmd.response_normalized = response_normalized or {}
        cmd.save(update_fields=["status", "completed_at",
                                 "response_raw", "response_normalized"])

        try:
            from core.metrics import device_commands_total
            device_commands_total.labels(kind=cmd.kind, status="completed").inc()
        except Exception:
            pass

        from .event_bus import EventBus
        EventBus.emit_command_completed(cmd.pk, cmd.device_id, cmd.kind,
                                         cmd.response_normalized)
        return cmd

    @staticmethod
    def fail(command_id, error_message: str):
        from devices.models import DeviceCommand
        try:
            cmd = DeviceCommand.objects.get(pk=command_id)
        except DeviceCommand.DoesNotExist:
            return None
        cmd.status = "failed"
        cmd.error_message = error_message[:500]
        cmd.completed_at = timezone.now()
        cmd.save(update_fields=["status", "error_message", "completed_at"])

        try:
            from core.metrics import device_commands_total
            device_commands_total.labels(kind=cmd.kind, status="failed").inc()
        except Exception:
            pass

        from .event_bus import EventBus
        EventBus.emit_command_failed(cmd.pk, cmd.device_id, cmd.kind, error_message)
        return cmd

    @staticmethod
    def sweep_timeouts():
        """À appeler périodiquement (Celery beat) — passe les commandes expirées en timeout."""
        from devices.models import DeviceCommand
        expired = DeviceCommand.objects.filter(
            status__in=["pending", "sent", "acknowledged"],
            timeout_at__lt=timezone.now(),
        )
        count = 0
        for cmd in expired:
            cmd.status = "timeout"
            cmd.completed_at = timezone.now()
            cmd.error_message = "Aucune réponse reçue dans le délai imparti"
            cmd.save(update_fields=["status", "completed_at", "error_message"])
            count += 1
        return count

    # ────────────────────────────────────────────────────────────
    # Pull (Agent local via HTTP long-poll fallback)
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def drain_for_device(device_id) -> list[dict]:
        """L'Agent local vient chercher les commandes en attente pour un device.

        Utilisé quand la WS n'est pas dispo (fallback HTTP polling).
        """
        key = CMD_QUEUE_KEY.format(device_id=device_id)
        items = cache.get(key) or []
        cache.delete(key)
        return items


# ═══════════════════════════════════════════════════════════════════
# Helpers privés
# ═══════════════════════════════════════════════════════════════════
def _push_redis_queue(device_id, payload: dict):
    key = CMD_QUEUE_KEY.format(device_id=device_id)
    items = cache.get(key) or []
    items.append(payload)
    # Cap 100
    if len(items) > 100:
        items = items[-100:]
    cache.set(key, items, CMD_TTL_SECONDS)


def _resolve_agent(device):
    """Cherche un LocalAgent responsable de ce device.

    Heuristique : agent du même site, en ligne. Extensible plus tard.
    """
    from devices.models import LocalAgent
    try:
        return LocalAgent.objects.filter(
            tenant=device.tenant, site=device.site, connected=True,
        ).first()
    except Exception:
        return None


def _is_adms_device(device) -> bool:
    """True si l'équipement suit le protocole ADMS pull (ZKTeco, AiFace)."""
    try:
        return device.model.type == "face_terminal"
    except Exception:
        return False


def _set_adms_command(device, kind: str, payload: dict):
    """Stocke une commande ADMS que le terminal récupérera au prochain heartbeat.

    Mapping des kinds vers les vraies commandes ADMS :
      RESTART_DEVICE → REBOOT
      SYNC_DEVICE    → CHECK
      START_RFID_ENROLLMENT → REG (mode enroll)
      READ_RFID_CARD → (le terminal push naturellement les lectures)
    """
    ADMS_MAP = {
        "RESTART_DEVICE":         "REBOOT",
        "SYNC_DEVICE":            "CHECK",
        "GET_DEVICE_INFO":        "INFO",
        "START_RFID_ENROLLMENT":  "REG",
        "STOP_RFID_ENROLLMENT":   "STOPREG",
    }
    cmd_str = ADMS_MAP.get(kind)
    if not cmd_str:
        return
    key = ADMS_CMD_KEY.format(serial=device.serial_number)
    cache.set(key, cmd_str, CMD_TTL_SECONDS)


def _try_http_direct(device, payload: dict):
    """POST HTTP direct vers le device (fire-and-forget dans un thread)."""
    import threading

    import requests

    def _do():
        url = f"http://{device.ip_address}/kshield/command"
        try:
            requests.post(url, json=payload, timeout=3)
        except Exception as exc:
            logger.debug("HTTP direct KO %s: %s", device.serial_number, exc)

    threading.Thread(target=_do, daemon=True).start()
