"""KAYDAN SHIELD — client MQTT côté serveur.

Subscribe aux topics IoT et injecte les événements dans les services.

Topics par défaut :
  ``kshield/<tenant_slug>/rfid/<device_serial>``  → payload JSON {"uid": "...", "rssi": -45}
  ``kshield/<tenant_slug>/ble/<gateway_serial>``  → payload JSON pour BLE
  ``kshield/<tenant_slug>/device/<device_serial>/status`` → statut heartbeat

Lancé par un management command dédié (``python manage.py mqtt_listen``).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class MqttListener:
    """Wrapper paho-mqtt qui pousse les messages vers les services.

    Utilisation :
        listener = MqttListener(host="localhost", port=1883)
        listener.start()      # non bloquant, lance un thread interne
        # ... plus tard
        listener.stop()
    """

    def __init__(self, host: str = "localhost", port: int = 1883,
                  username: Optional[str] = None, password: Optional[str] = None,
                  topic_prefix: str = "kshield/#",
                  client_id: str = "kshield-server",
                  tls: bool = False, ca_file: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client_id = client_id
        self.tls = tls
        self.ca_file = ca_file
        self._client = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True,
                                          name="mqtt-listener")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    # ────────────────────────────────────────────────────────────
    # Boucle interne
    # ────────────────────────────────────────────────────────────
    def _run(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt non installé — pip install paho-mqtt")
            return

        self._client = mqtt.Client(client_id=self.client_id)
        if self.username:
            self._client.username_pw_set(self.username, self.password or "")
        if self.tls:
            self._client.tls_set(ca_certs=self.ca_file)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        while not self._stop.is_set():
            try:
                self._client.connect(self.host, self.port, keepalive=60)
                self._client.loop_forever(retry_first_connection=False)
            except Exception as exc:
                logger.warning("MQTT down : %s — retry in 5s", exc)
                time.sleep(5)

    def _on_connect(self, client, userdata, flags, rc):
        logger.info("MQTT connecté (rc=%s) — subscribe %s", rc, self.topic_prefix)
        client.subscribe(self.topic_prefix, qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            logger.warning("Payload MQTT non-JSON %s", msg.topic)
            return
        logger.debug("MQTT %s → %s", msg.topic, payload)

        parts = msg.topic.split("/")
        if len(parts) < 3 or parts[0] != "kshield":
            return

        # ─── Topic Edge Gateway (Go agent) ─────────────────────────
        # kshield/edge/<gateway_id>/events    → batch events
        # kshield/edge/<gateway_id>/status    → heartbeat compact
        # kshield/edge/<gateway_id>/scan      → résultat scan réseau
        if parts[1] == "edge" and len(parts) >= 4:
            gateway_id = parts[2]
            sub = parts[3]
            if sub == "events":
                self._forward_edge_events(gateway_id, payload)
                return
            if sub == "status":
                self._forward_edge_status(gateway_id, payload)
                return
            if sub == "scan":
                self._forward_edge_scan(gateway_id, payload)
                return

        # ─── Topics devices legacy : kshield/<tenant>/<kind>/<serial> ──
        if len(parts) < 4:
            return
        _, _tenant_slug, kind, serial = parts[0], parts[1], parts[2], parts[3]

        if kind == "rfid":
            self._forward_rfid(serial, payload)
        elif kind == "ble":
            self._forward_ble(serial, payload)
        elif kind == "device" and len(parts) >= 5 and parts[4] == "status":
            self._forward_status(serial, payload)

    # ────────────────────────────────────────────────────────────
    # Forwarders
    # ────────────────────────────────────────────────────────────
    def _forward_rfid(self, serial: str, payload: dict):
        from devices.models import Device
        from .enrollment import EnrollmentError, RFIDEnrollmentService

        try:
            device = Device.objects.get(serial_number=serial)
        except Device.DoesNotExist:
            logger.warning("Device MQTT inconnu : %s", serial)
            return

        uid = payload.get("uid") or payload.get("card_id")
        if not uid:
            return
        try:
            RFIDEnrollmentService.ingest_scan(
                tenant=device.tenant, uid=str(uid), device=device,
                rssi=payload.get("rssi"),
                extra=payload.get("extra") or {},
            )
        except EnrollmentError as exc:
            logger.warning("Ingest MQTT KO: %s", exc)

    def _forward_ble(self, serial: str, payload: dict):
        # Placeholder — sera relié à un service BLE dédié si besoin
        logger.debug("BLE scan reçu %s: %s", serial, payload)

    def _forward_status(self, serial: str, payload: dict):
        from devices.models import Device

        from django.utils import timezone
        try:
            device = Device.objects.get(serial_number=serial)
        except Device.DoesNotExist:
            return
        device.last_heartbeat_at = timezone.now()
        if "battery_level" in payload:
            device.battery_level = int(payload["battery_level"])
        device.save(update_fields=["last_heartbeat_at", "battery_level"])

    # ────────────────────────────────────────────────────────────
    # Edge Gateway forwarders (Phase 2.3)
    # ────────────────────────────────────────────────────────────
    def _forward_edge_events(self, gateway_id: str, payload: dict):
        """kshield/edge/<gid>/events — batch d'events métier.

        Le payload est le shape EventBatch envoyé par l'agent Go via MQTT
        en complément du POST HTTP (redondance).
        """
        from devices.models import LocalAgent
        try:
            agent = LocalAgent.objects.get(pk=gateway_id)
        except LocalAgent.DoesNotExist:
            logger.warning("MQTT events pour gateway inconnue: %s", gateway_id)
            return
        events = payload.get("events") or []
        logger.info("MQTT batch %d events depuis gateway %s (label=%s)",
                     len(events), gateway_id, agent.label)
        # TODO : implémenter le dispatch dans les services métier.
        # Pour l'instant on log — le canal HTTP est primary et fait déjà le taf.

    def _forward_edge_status(self, gateway_id: str, payload: dict):
        """kshield/edge/<gid>/status — heartbeat compact (complémentaire HTTP)."""
        from devices.models import LocalAgent
        from django.utils import timezone
        try:
            agent = LocalAgent.objects.get(pk=gateway_id)
        except LocalAgent.DoesNotExist:
            return
        agent.last_seen_at = timezone.now()
        if payload.get("uptime_seconds") is not None:
            agent.uptime_seconds = int(payload["uptime_seconds"])
        if payload.get("events_pending") is not None:
            agent.events_pending = int(payload["events_pending"])
        agent.save(update_fields=["last_seen_at", "uptime_seconds", "events_pending"])

    def _forward_edge_scan(self, gateway_id: str, payload: dict):
        """kshield/edge/<gid>/scan — résultat scan réseau."""
        from devices.models import LocalAgent
        try:
            agent = LocalAgent.objects.get(pk=gateway_id)
        except LocalAgent.DoesNotExist:
            return
        devs = payload.get("devices") or []
        if isinstance(devs, list):
            agent.devices_discovered = devs[:500]
            agent.save(update_fields=["devices_discovered"])
            logger.info("MQTT scan gateway %s → %d devices", gateway_id, len(devs))
