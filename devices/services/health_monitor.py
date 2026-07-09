"""KAYDAN SHIELD — supervision périodique de la santé des équipements.

Objectif : détecter les transitions online↔offline et publier les events pour
que le front reçoive un statut à jour sans rafraîchir toute la liste.

Utilisation (Celery beat) :
    from devices.services import EquipmentHealthMonitor
    EquipmentHealthMonitor.tick()   # à lancer toutes les 30-60 sec
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Seuil au-delà duquel un device sans heartbeat est considéré offline
HEARTBEAT_TIMEOUT_SECONDS = 120


class EquipmentHealthMonitor:
    """Passage périodique — met à jour les statuts et émet des events."""

    @staticmethod
    def tick():
        """À appeler périodiquement (Celery beat toutes les 30-60s)."""
        from devices.models import Device
        from .event_bus import EventBus

        cutoff = timezone.now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

        # Devices marqués "active" mais sans heartbeat récent → considérés offline
        offline_candidates = Device.objects.filter(
            status="active", last_heartbeat_at__lt=cutoff,
        ).exclude(last_heartbeat_at__isnull=True)

        transitioned = 0
        for d in offline_candidates:
            EventBus.emit_device_disconnected(d.pk, d.serial_number)
            transitioned += 1

        # Devices avec heartbeat récent mais qui étaient offline → transition back
        online_devices = Device.objects.filter(
            status="active", last_heartbeat_at__gte=cutoff,
        )
        for d in online_devices:
            # Emet seulement si la dernière transition connue est différente
            # (simplifié : on n'a pas de cache de statut → on émet à chaque tick,
            # les listeners sont supposés idempotents)
            EventBus.emit_device_connected(d.pk, d.serial_number)

        logger.debug("HealthMonitor tick: %d offline transitions", transitioned)
        return {
            "offline_transitions": transitioned,
            "checked": offline_candidates.count() + online_devices.count(),
        }

    @staticmethod
    def probe(device):
        """Ping ponctuel d'un device — retourne dict avec latence et statut."""
        import socket
        import time

        if not device.ip_address:
            return {"reachable": False, "reason": "no_ip"}

        ports = _ports_for(device)
        for port in ports:
            try:
                t0 = time.perf_counter()
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    if s.connect_ex((device.ip_address, port)) == 0:
                        return {
                            "reachable": True,
                            "port": port,
                            "latency_ms": int((time.perf_counter() - t0) * 1000),
                        }
            except Exception:
                continue
        return {"reachable": False, "reason": "no_port_open", "ports_tried": ports}


def _ports_for(device) -> list[int]:
    type_map = {
        "face_terminal":     [4370, 80, 8080, 443],
        "portique":          [5084, 80, 8080],
        "camera":            [554, 80, 8080, 3702, 443],
        "reader_uhf_fixed":  [5084, 80, 8080],
        "reader_uhf_mobile": [5084, 80, 8080],
        "reader_nfc_fixed":  [80, 8080, 443],
        "reader_nfc_mobile": [80, 8080, 443],
    }
    t = getattr(getattr(device, "model", None), "type", None) or ""
    return type_map.get(t, [80, 443, 4370, 5084, 554, 8080])
