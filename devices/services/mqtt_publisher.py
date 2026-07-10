"""Publisher MQTT pour push commandes → gateways Edge.

Utilise paho-mqtt en mode synchrone (publish + wait ack). Instance
singleton partagée via LRU pour éviter de recréer une connexion à chaque
appel.

Utilisation typique :
    from devices.services.mqtt_publisher import publish_command
    publish_command(gateway_id="abc-123", action_type="restart",
                     payload={"reason": "manual admin trigger"})
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# Singleton client — on garde une connexion persistante pour minimiser
# les allers-retours TCP à chaque publish.
_client_lock = threading.Lock()
_client = None
_client_last_error: Optional[Exception] = None


def _get_client():
    """Retourne le client paho connecté (lazy init + auto-reconnect)."""
    global _client, _client_last_error
    with _client_lock:
        if _client is not None:
            try:
                if _client.is_connected():
                    return _client
            except Exception:
                pass
            # Reconnexion silencieuse
            try:
                _client.loop_stop()
                _client.disconnect()
            except Exception:
                pass
            _client = None

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt requis — pip install paho-mqtt")
            return None

        host = getattr(settings, "MQTT_HOST", "shieldmqtt")
        port = int(getattr(settings, "MQTT_PORT", 1883))
        user = getattr(settings, "MQTT_USERNAME", "")
        pwd = getattr(settings, "MQTT_PASSWORD", "")
        use_tls = bool(getattr(settings, "MQTT_TLS", False))
        ca_file = getattr(settings, "MQTT_CA_FILE", "")
        client_id_prefix = getattr(settings, "MQTT_CLIENT_ID_PREFIX", "kshield-django")

        client_id = f"{client_id_prefix}-publisher-{uuid.uuid4().hex[:8]}"
        c = mqtt.Client(client_id=client_id, clean_session=True)
        if user:
            c.username_pw_set(user, pwd or "")
        if use_tls:
            c.tls_set(ca_certs=ca_file if ca_file else None)
        c.max_inflight_messages_set(20)
        c.reconnect_delay_set(min_delay=1, max_delay=60)

        try:
            c.connect(host, port, keepalive=60)
        except Exception as exc:
            _client_last_error = exc
            logger.warning("MQTT publisher connect échoué (%s:%s): %s",
                            host, port, exc)
            return None

        c.loop_start()
        # Attend jusqu'à 3s la confirmation de connexion
        for _ in range(30):
            if c.is_connected():
                break
            time.sleep(0.1)
        if not c.is_connected():
            logger.warning("MQTT publisher pas connecté après 3s")
            _client_last_error = TimeoutError("connect timeout")
            try:
                c.loop_stop()
            except Exception:
                pass
            return None

        _client = c
        _client_last_error = None
        logger.info("MQTT publisher connecté: %s:%s user=%s", host, port, user)
        return _client


def publish_command(
    gateway_id: str,
    action_type: str,
    payload: Optional[Dict[str, Any]] = None,
    qos: int = 1,
) -> Dict[str, Any]:
    """Publie une commande sur le topic dédié d'une gateway.

    Topic : ``kshield/cmd/edge/<gateway_id>/<action_type>``

    Args:
        gateway_id  : UUID de la LocalAgent cible
        action_type : "restart" | "force_sync" | "scan_network" | "update" | ...
        payload     : Dict optionnel injecté dans le message
        qos         : QoS MQTT (défaut 1 — au moins une fois)

    Returns:
        Dict avec 'ok': bool, 'action_id': str, 'error': str (si !ok)
    """
    action_id = uuid.uuid4().hex

    msg = {
        "id": action_id,
        "type": action_type,
        "payload": payload or {},
        "issued_at": int(time.time()),
    }
    topic = f"kshield/cmd/edge/{gateway_id}/{action_type}"
    body = json.dumps(msg)

    c = _get_client()
    if c is None:
        return {
            "ok": False,
            "action_id": action_id,
            "error": f"MQTT publisher indisponible: {_client_last_error}",
        }

    try:
        info = c.publish(topic, body, qos=qos)
        info.wait_for_publish(timeout=5)
        if info.rc != 0:
            return {
                "ok": False,
                "action_id": action_id,
                "error": f"MQTT publish rc={info.rc}",
            }
        logger.debug("MQTT publish OK: gateway=%s action=%s id=%s",
                     gateway_id, action_type, action_id)
        return {
            "ok": True,
            "action_id": action_id,
            "topic": topic,
        }
    except Exception as exc:
        logger.exception("MQTT publish échoué")
        return {"ok": False, "action_id": action_id, "error": str(exc)}


def publish_broadcast(action_type: str, payload: Optional[Dict[str, Any]] = None,
                       qos: int = 0) -> Dict[str, Any]:
    """Publie un broadcast à toutes les gateways (topic dédié)."""
    action_id = uuid.uuid4().hex
    msg = {
        "id": action_id,
        "type": action_type,
        "payload": payload or {},
        "issued_at": int(time.time()),
        "broadcast": True,
    }
    topic = f"kshield/cmd/broadcast/{action_type}"
    body = json.dumps(msg)

    c = _get_client()
    if c is None:
        return {"ok": False, "error": f"MQTT indisponible: {_client_last_error}"}

    try:
        info = c.publish(topic, body, qos=qos)
        info.wait_for_publish(timeout=3)
        return {"ok": info.rc == 0, "action_id": action_id, "topic": topic}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close_publisher():
    """Ferme le singleton — utile en test / shutdown Django."""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.loop_stop()
                _client.disconnect()
            except Exception:
                pass
            _client = None
