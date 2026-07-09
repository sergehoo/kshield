"""Adaptateurs pour parler aux lecteurs physiques présents sur le LAN client.

Chaque adaptateur expose la même interface asynchrone :
    async def start(on_card: Callable[[dict], Awaitable[None]]): ...
    async def stop(): ...
    async def execute_command(cmd: dict) -> dict: ...

``on_card`` est appelée à chaque UID lu. Le payload doit ressembler à :
    {"uid": "AABBCC01", "device_id": 42, "rssi": -47, "extra": {...}}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class ReaderAdapter:
    """Classe de base — sous-classée par chaque protocole."""
    kind: str = "base"

    def __init__(self, cfg):
        self.cfg = cfg
        self._running = False

    async def start(self, on_card: Callable[[dict], Awaitable[None]]):
        raise NotImplementedError

    async def stop(self):
        self._running = False

    async def execute_command(self, cmd: dict) -> dict:
        """Exécute une commande DeviceCommand pour ce lecteur.

        Retourne un dict ``{"status": "ok" | "error", "detail": ..., "raw": ...}``.
        """
        return {"status": "error", "detail": f"kind={self.kind} ne supporte pas les commandes"}


# ═══════════════════════════════════════════════════════════════════
# ZKTeco / AiFace via pyzk — poll toutes les 3s
# ═══════════════════════════════════════════════════════════════════
class ZktecoReader(ReaderAdapter):
    kind = "zkteco"

    async def start(self, on_card):
        self._running = True
        self._on_card = on_card
        # Pour éviter les doublons entre polls
        self._seen = set()
        while self._running:
            try:
                await asyncio.to_thread(self._poll_once)
            except Exception as exc:
                logger.warning("ZKTeco poll KO %s: %s", self.cfg.ip, exc)
            await asyncio.sleep(self.cfg.poll_seconds)

    def _poll_once(self):
        try:
            from zk import ZK
        except ImportError:
            logger.error("pyzk non installé — pip install pyzk")
            return
        conn = None
        try:
            zk = ZK(self.cfg.ip, port=self.cfg.port, timeout=3,
                     password=int(self.cfg.extra.get("password", 0)))
            conn = zk.connect()
            atts = conn.get_attendance() or []
            for a in atts:
                key = (a.user_id, a.timestamp.isoformat())
                if key in self._seen:
                    continue
                self._seen.add(key)
                # AJoute au callback via loop principal
                asyncio.run_coroutine_threadsafe(
                    self._on_card({
                        "uid": str(a.user_id),   # user_id ZK; card=… si mappé
                        "device_id": self.cfg.device_id,
                        "rssi": None,
                        "extra": {"raw_zk_status": a.status, "punch": a.punch},
                    }),
                    asyncio.get_event_loop(),
                )
        except Exception as exc:
            logger.warning("ZKTeco read KO %s: %s", self.cfg.ip, exc)
        finally:
            if conn is not None:
                try: conn.disconnect()
                except Exception: pass

    async def execute_command(self, cmd: dict) -> dict:
        kind = cmd.get("kind")
        if kind == "PING_DEVICE":
            import socket
            try:
                with socket.create_connection((self.cfg.ip, self.cfg.port), timeout=1.5):
                    return {"status": "ok", "detail": "reachable"}
            except Exception as exc:
                return {"status": "error", "detail": str(exc)}
        return await super().execute_command(cmd)


# ═══════════════════════════════════════════════════════════════════
# HTTP webhook — l'agent expose un serveur local que le lecteur appelle
# ═══════════════════════════════════════════════════════════════════
class HttpWebhookReader(ReaderAdapter):
    """Lecteur qui push chaque UID en HTTP POST vers l'agent.

    L'agent ouvre un port local (par défaut 8765) et écoute :
        POST /rfid/scan  {"uid": "AABBCC01"}
    """
    kind = "http_webhook"

    async def start(self, on_card):
        self._running = True
        self._on_card = on_card
        from aiohttp import web
        app = web.Application()
        app.router.add_post("/rfid/scan", self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(self.cfg.extra.get("listen_port", 8765))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("HttpWebhookReader écoute sur :%d", port)

    async def _handle(self, request):
        from aiohttp import web
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        uid = data.get("uid") or data.get("card_id")
        if not uid:
            return web.json_response({"error": "uid manquant"}, status=400)
        await self._on_card({
            "uid": str(uid),
            "device_id": self.cfg.device_id,
            "rssi": data.get("rssi"),
            "extra": data.get("extra") or {},
        })
        return web.json_response({"ok": True})


# ═══════════════════════════════════════════════════════════════════
# LLRP (Impinj/Zebra) — client sllurp complet
# ═══════════════════════════════════════════════════════════════════
class LlrpReader(ReaderAdapter):
    """Client LLRP pour portiques Impinj / Zebra / MotorolaSolutions.

    Utilise ``sllurp`` (installé via extras : pip install kshield-agent[llrp]).
    Les tags UHF captés sont pushés au callback via ``on_card`` avec :
        {"uid": "<EPC hex>", "rssi": <int>, "device_id": ..., "extra": {"antenna": 1, ...}}
    """
    kind = "llrp"

    async def start(self, on_card):
        self._running = True
        self._on_card = on_card
        loop = asyncio.get_running_loop()

        try:
            from sllurp.llrp import LLRPClientFactory
            from sllurp.reactor import DefaultReactor
            from twisted.internet import reactor as twisted_reactor
        except ImportError:
            logger.error(
                "sllurp non installé — pip install sllurp. LlrpReader %s en veille.",
                self.cfg.ip,
            )
            while self._running:
                await asyncio.sleep(30)
            return

        def _on_tags(reader_state, tags):
            """Callback synchrone appelé par le reactor Twisted."""
            for t in tags or []:
                epc = t.get("EPC-96") or t.get("EPC") or ""
                if isinstance(epc, bytes):
                    epc = epc.hex().upper()
                if not epc:
                    continue
                payload = {
                    "uid": epc,
                    "device_id": self.cfg.device_id,
                    "rssi": t.get("PeakRSSI"),
                    "extra": {
                        "antenna": t.get("AntennaID"),
                        "read_count": t.get("TagSeenCount"),
                        "channel": t.get("ChannelIndex"),
                    },
                }
                # Bounce vers la loop asyncio (thread-safe)
                asyncio.run_coroutine_threadsafe(self._on_card(payload), loop)

        try:
            factory = LLRPClientFactory(
                report_every_n=1,
                antennas=(self.cfg.extra.get("antennas") or [1]),
                tx_power=self.cfg.extra.get("tx_power", 0),
                start_inventory=True,
                disconnect_when_done=False,
                reconnect=True,
                tag_content_selector={
                    "EnableAntennaID": True,
                    "EnableFirstSeenTimestamp": True,
                    "EnablePeakRSSI": True,
                    "EnableRFPhaseAngle": False,
                    "EnableTagSeenCount": True,
                },
            )
            factory.addTagReportCallback(_on_tags)
            # Connect via reactor Twisted, non bloquant
            twisted_reactor.callFromThread(
                twisted_reactor.connectTCP,
                self.cfg.ip, self.cfg.port or 5084, factory,
            )
            logger.info("LlrpReader connecté à %s:%d", self.cfg.ip, self.cfg.port or 5084)
        except Exception as exc:
            logger.exception("LlrpReader %s init KO : %s", self.cfg.ip, exc)

        # Boucle vide — le reactor Twisted tourne dans son thread
        while self._running:
            await asyncio.sleep(5)

    async def execute_command(self, cmd):
        kind = cmd.get("kind")
        if kind == "PING_DEVICE":
            import socket
            try:
                with socket.create_connection((self.cfg.ip, self.cfg.port or 5084), timeout=1.5):
                    return {"status": "ok", "detail": "LLRP port ouvert"}
            except Exception as exc:
                return {"status": "error", "detail": str(exc)}
        return await super().execute_command(cmd)


# ═══════════════════════════════════════════════════════════════════
# NFC USB PC/SC (ACR122U, uTrust 3700F, etc.) via pyscard
# ═══════════════════════════════════════════════════════════════════
class NfcPcscReader(ReaderAdapter):
    """Lecteur NFC USB via l'API PC/SC (Windows/Linux/macOS).

    Détecte automatiquement les cartes présentées, envoie APDU ``GetUID`` (FF CA 00 00 00),
    parse la réponse en hex → UID. Testé avec ACR122U, ACR1252U, HID Omnikey.

    Nécessite ``pyscard`` installé sur la machine cliente.
    """
    kind = "nfc_pcsc"

    async def start(self, on_card):
        self._running = True
        self._on_card = on_card

        try:
            from smartcard.System import readers
            from smartcard.util import toHexString
            from smartcard.Exceptions import CardConnectionException, NoCardException
        except ImportError:
            logger.error("pyscard non installé — pip install pyscard. NfcPcscReader en veille.")
            while self._running:
                await asyncio.sleep(30)
            return

        # APDU standard PC/SC "Get UID" (ISO/IEC 14443-3)
        GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        target_reader_name = self.cfg.extra.get("reader_name", "").lower()
        seen_uids: set[str] = set()
        loop = asyncio.get_running_loop()

        def _read_once():
            """Lecture synchrone d'une carte présente (poll pattern)."""
            try:
                reader_list = readers()
            except Exception as exc:
                logger.warning("PC/SC readers() KO : %s", exc)
                return None
            if not reader_list:
                return None

            # Choix du lecteur
            chosen = None
            for r in reader_list:
                if not target_reader_name or target_reader_name in str(r).lower():
                    chosen = r
                    break
            if chosen is None:
                return None

            try:
                conn = chosen.createConnection()
                conn.connect()
                data, sw1, sw2 = conn.transmit(GET_UID_APDU)
                conn.disconnect()
                if sw1 == 0x90 and sw2 == 0x00:
                    return toHexString(data).replace(" ", "")
            except (NoCardException, CardConnectionException):
                return None
            except Exception as exc:
                logger.debug("PC/SC transmit KO : %s", exc)
                return None
            return None

        logger.info("NfcPcscReader démarré (poll %ss)", self.cfg.poll_seconds)
        while self._running:
            try:
                uid = await asyncio.to_thread(_read_once)
            except Exception as exc:
                logger.warning("NfcPcscReader read KO : %s", exc)
                uid = None

            if uid and uid not in seen_uids:
                seen_uids.add(uid)
                # Le buffer se vide au bout de 30s pour permettre re-scan de la même carte
                asyncio.get_event_loop().call_later(30, lambda u=uid: seen_uids.discard(u))
                await self._on_card({
                    "uid": uid,
                    "device_id": self.cfg.device_id,
                    "rssi": None,
                    "extra": {"transport": "pc/sc"},
                })
            await asyncio.sleep(max(self.cfg.poll_seconds or 1, 0.5))

    async def execute_command(self, cmd):
        # Les lecteurs USB PC/SC n'acceptent pas de commandes distantes
        return {"status": "ok", "detail": "NFC PC/SC — pas de commande à distance"}


# ═══════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════
KIND_MAP: dict[str, type[ReaderAdapter]] = {
    "zkteco":       ZktecoReader,
    "http_webhook": HttpWebhookReader,
    "llrp":         LlrpReader,
    "nfc_pcsc":     NfcPcscReader,
}


def build_reader(cfg) -> ReaderAdapter:
    cls = KIND_MAP.get(cfg.kind)
    if cls is None:
        raise ValueError(f"kind lecteur inconnu : {cfg.kind}")
    return cls(cfg)
