"""Client WebSocket persistant vers /ws/agents/<id>/.

Boucle principale :
  * Connexion WS avec reconnexion exponentielle
  * Réception des commandes → dispatch vers ReaderAdapter concerné
  * Envoi des scans RFID captés par les readers
  * Heartbeat périodique
  * Fallback HTTP polling si WS impossible pendant N tentatives
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
import websockets

from .config import AgentConfig
from .offline_queue import DEFAULT_QUEUE_PATH, OfflineQueue
from .readers import ReaderAdapter, build_reader
from .signing import sign_payload

logger = logging.getLogger(__name__)


class AgentClient:
    """Orchestrateur agent."""

    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.readers: list[ReaderAdapter] = [build_reader(r) for r in cfg.readers]
        self._ws: Any = None
        self._ws_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        # Queue offline SQLite — événements écrits quand WS + HTTP sont down
        queue_path = getattr(cfg, "offline_queue_path", None) or DEFAULT_QUEUE_PATH
        self.offline_queue = OfflineQueue(queue_path)

    # ────────────────────────────────────────────────────────────
    # Entrée / arrêt
    # ────────────────────────────────────────────────────────────
    async def run(self):
        """Boucle principale — lance readers + WS + heartbeat + replay en parallèle."""
        tasks = [asyncio.create_task(r.start(self._on_card)) for r in self.readers]
        tasks.append(asyncio.create_task(self._ws_loop()))
        tasks.append(asyncio.create_task(self._heartbeat_loop()))
        tasks.append(asyncio.create_task(self._offline_replay_loop()))
        try:
            await self._stop.wait()
        finally:
            for r in self.readers:
                await r.stop()
            for t in tasks:
                t.cancel()

    async def stop(self):
        self._stop.set()

    # ────────────────────────────────────────────────────────────
    # WebSocket
    # ────────────────────────────────────────────────────────────
    async def _ws_loop(self):
        attempt = 0
        while not self._stop.is_set():
            try:
                logger.info("WS connect %s", self.cfg.ws_url)
                async with websockets.connect(
                    self.cfg.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    self._ws = ws
                    attempt = 0
                    logger.info("WS connectée")
                    await self._on_ws_open()
                    async for raw in ws:
                        await self._handle_ws_message(raw)
            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                logger.warning("WS down : %s", exc)
            except Exception as exc:
                logger.exception("WS erreur inattendue : %s", exc)
            self._ws = None
            if self._stop.is_set():
                return
            attempt += 1
            delay = min(2 ** attempt, self.cfg.reconnect_max_seconds)
            logger.info("WS retry dans %ds", delay)
            await asyncio.sleep(delay)

    async def _on_ws_open(self):
        # Handshake : envoie la version + os
        import platform
        await self._ws.send(json.dumps({
            "event": "agent.hello",
            "version": "0.1.0",
            "os": platform.platform(),
        }))

    async def _handle_ws_message(self, raw: str | bytes):
        try:
            msg = json.loads(raw)
        except Exception:
            logger.warning("WS message non-JSON: %r", raw[:200])
            return

        # Cas 1 : commande push serveur
        if "command" in msg:
            cmd = msg["command"]
            await self._dispatch_command(cmd)
            return

        # Cas 2 : hello / pong / autres
        if msg.get("type") == "hello":
            logger.info("Serveur %s", msg.get("welcome", ""))
            return

        # Cas 3 : actions admin poussées par EventBus.push_to_agent
        action = msg.get("action")
        if action:
            await self._handle_admin_action(action, msg)

    async def _handle_admin_action(self, action: str, msg: dict):
        logger.info("Action admin reçue : %s", action)
        if action == "restart":
            # Signale le stop propre ; systemd (ou docker) redémarre.
            self._stop.set()
        elif action == "force_sync":
            # Rejoue la queue offline immédiatement
            events = self.offline_queue.peek(limit=200)
            for e in events:
                sent = await self._ws_send(e["payload"])
                if not sent:
                    sent = await self._http_post_event(e["payload"])
                if sent:
                    self.offline_queue.ack(e["id"])
        elif action == "scan_network":
            from .discovery import scan_local_network
            try:
                devices = await scan_local_network(
                    timeout_per_ip=float(msg.get("timeout") or 0.5),
                    max_ips=int(msg.get("max_ips") or 254),
                )
            except Exception as exc:
                logger.exception("Agent scan KO : %s", exc)
                devices = []
            await self._ws_send({
                "event": "scan_network.result",
                "count": len(devices),
                "devices": devices,
            })
            # Push aussi via HTTP pour persister dans devices_discovered
            await self._http_post_event({
                "event": "scan_network.result",
                "devices_discovered": devices,
            })
        elif action == "update":
            # Ne fait rien de destructif — laisse un installateur externe agir.
            logger.info("Update demandé : %s", msg.get("package_url"))
            await self._ws_send({"event": "update.acknowledged",
                                    "package_id": msg.get("package_id")})

    async def _dispatch_command(self, cmd: dict):
        cmd_id = cmd.get("command_id")
        device_id = cmd.get("device_id")
        kind = cmd.get("kind")
        logger.info("Commande %s (%s) → device %s", cmd_id, kind, device_id)

        # Ack immédiat
        await self._ws_send({
            "event": "device.command.ack",
            "command_id": cmd_id,
        })

        # Trouve le reader qui gère ce device
        target = None
        for r in self.readers:
            if r.cfg.device_id == device_id:
                target = r
                break

        if target is None:
            await self._ws_send({
                "event": "device.command.failed",
                "command_id": cmd_id,
                "error": f"aucun reader local pour device_id={device_id}",
            })
            return

        try:
            result = await target.execute_command(cmd)
            if result.get("status") == "ok":
                await self._ws_send({
                    "event": "device.command.completed",
                    "command_id": cmd_id,
                    "response_raw": result.get("raw") or {},
                    "response_normalized": result,
                })
            else:
                await self._ws_send({
                    "event": "device.command.failed",
                    "command_id": cmd_id,
                    "error": result.get("detail") or "unknown",
                })
        except Exception as exc:
            logger.exception("execute_command KO")
            await self._ws_send({
                "event": "device.command.failed",
                "command_id": cmd_id,
                "error": str(exc),
            })

    # ────────────────────────────────────────────────────────────
    # Envoi de scans
    # ────────────────────────────────────────────────────────────
    async def _on_card(self, payload: dict):
        logger.debug("Card lue: %s", payload)
        message = {
            "event": "rfid.card.detected",
            **payload,
        }
        # Priorité 1 : WebSocket
        if await self._ws_send(message):
            return
        # Priorité 2 : HTTP direct
        if await self._http_post_event(message):
            return
        # Priorité 3 : offline queue (rejeu automatique)
        self.offline_queue.enqueue("event", message)
        logger.info("Event mis en offline queue (WS et HTTP down)")

    async def _ws_send(self, payload: dict) -> bool:
        if self._ws is None:
            return False
        try:
            await self._ws.send(json.dumps(payload))
            return True
        except Exception as exc:
            logger.warning("WS send KO: %s", exc)
            return False

    async def _http_post_event(self, message: dict) -> bool:
        """Fallback HTTP quand la WS est down. Retourne True si succès."""
        url = f"{self.cfg.http_base}/devices/agent/{self.cfg.agent_id}/events/"
        headers = {"Authorization": f"Bearer {self.cfg.api_token}"}
        if self.cfg.hmac_secret:
            ts, sig = sign_payload(self.cfg.hmac_secret, message)
            headers["X-Kshield-Timestamp"] = ts
            headers["X-Kshield-Signature"] = sig
        try:
            async with httpx.AsyncClient(timeout=5) as http:
                r = await http.post(url, json=message, headers=headers)
                if r.status_code < 400:
                    return True
                logger.warning("HTTP fallback %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.warning("HTTP fallback KO: %s", exc)
        return False

    async def _offline_replay_loop(self):
        """Rejoue les événements en attente dès qu'une voie de sortie est dispo."""
        while not self._stop.is_set():
            await asyncio.sleep(15)
            stats = self.offline_queue.stats()
            if stats["pending"] == 0:
                continue
            # Test rapide : WS ouverte ?
            if self._ws is None:
                # Essaie quand même via HTTP (au cas où le serveur soit joignable)
                pass

            events = self.offline_queue.peek(limit=50)
            if not events:
                continue
            logger.info("Offline replay : %d événements à renvoyer (%d dead)",
                         len(events), stats["dead"])

            for e in events:
                sent = await self._ws_send(e["payload"])
                if not sent:
                    sent = await self._http_post_event(e["payload"])
                if sent:
                    self.offline_queue.ack(e["id"])
                else:
                    self.offline_queue.fail(e["id"],
                                              "aucune voie de sortie disponible")
                    # Si le premier échoue, inutile d'insister maintenant
                    break

    # ────────────────────────────────────────────────────────────
    # Heartbeat
    # ────────────────────────────────────────────────────────────
    async def _heartbeat_loop(self):
        import platform
        import socket
        boot_ts = time.time()

        def _local_ip():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    return s.getsockname()[0]
            except Exception:
                return None

        while not self._stop.is_set():
            await asyncio.sleep(self.cfg.heartbeat_seconds)
            stats = self.offline_queue.stats()
            payload = {
                "event": "heartbeat",
                "ts": int(time.time()),
                "uptime_seconds": int(time.time() - boot_ts),
                "events_pending": stats["pending"],
                "ip_local": _local_ip(),
                "os_info": f"{platform.system()} {platform.release()}",
                "version": "0.1.0",
                "mqtt_status": "unknown",
                "ws_status": "ok" if self._ws else "down",
                "cloud_status": "ok" if self._ws else "degraded",
            }
            # 1. Via WS si possible
            if not await self._ws_send(payload):
                # 2. Fallback HTTP POST /edge-gateway/heartbeat/
                await self._http_heartbeat(payload)

    async def _http_heartbeat(self, payload: dict):
        """Fallback HTTP quand WS down — pousse un heartbeat via l'endpoint dédié."""
        url = f"{self.cfg.http_base}/devices/edge-gateway/heartbeat/"
        headers = {"Authorization": f"Bearer {self.cfg.api_token}"}
        if self.cfg.hmac_secret:
            ts, sig = sign_payload(self.cfg.hmac_secret, payload)
            headers["X-Kshield-Timestamp"] = ts
            headers["X-Kshield-Signature"] = sig
        try:
            async with httpx.AsyncClient(timeout=5) as http:
                await http.post(url, json=payload, headers=headers)
        except Exception as exc:
            logger.debug("HTTP heartbeat KO : %s", exc)
