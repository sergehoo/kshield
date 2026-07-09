"""KAYDAN SHIELD — Driver ZKTeco / AiFace.

Wrappe le client historique ``devices.zk_client`` (basé sur pyzk) dans
l'interface ``BaseDriver`` du Driver Framework.

Modèles supportés (whitelist par brand, tout modèle passe) :
    - ZKTeco iClock 260/580/680, F18, K40
    - AiFace ai810, ai820, AYUC…
    - Toute variante ADMS-compatible
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterable, Optional

from ..base import (BaseDriver, Capability, DeviceEvent, DeviceInfo, DeviceStatus,
                     DriverResult, register_driver)

logger = logging.getLogger(__name__)


@register_driver
class ZktecoDriver(BaseDriver):
    """Driver pour terminaux ZKTeco / AiFace (protocole ADMS pull + push)."""

    vendor = "zkteco"
    supported_models = ("iClock", "K40", "F18", "K30", "ai810", "ai820",
                         "AiFace", "AYUC", "UF100", "SF200")
    capabilities = (
        Capability.PING,
        Capability.GET_INFO,
        Capability.GET_STATUS,
        Capability.READ_EVENTS,
        Capability.ENROLL_RFID,
        Capability.SYNC_ATTENDANCES,
        Capability.RESTART,
        Capability.PUSH_USER,
    )

    # ────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────
    def connect(self) -> DriverResult:
        if not self.device.ip_address:
            return DriverResult(ok=False, detail="Pas d'IP renseignée")
        self._connected = True
        return DriverResult(ok=True)

    def disconnect(self) -> DriverResult:
        self._connected = False
        return DriverResult(ok=True)

    # ────────────────────────────────────────────────────────────
    # Health checks
    # ────────────────────────────────────────────────────────────
    def ping(self) -> DriverResult:
        import socket
        if not self.device.ip_address:
            return DriverResult(ok=False, detail="Pas d'IP")
        port = self._zk_port()
        t0 = time.perf_counter()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                if s.connect_ex((self.device.ip_address, port)) == 0:
                    return DriverResult(
                        ok=True, detail="reachable",
                        data={"port": port,
                               "latency_ms": int((time.perf_counter() - t0) * 1000)},
                    )
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail=f"port {port} fermé")

    def get_status(self) -> DeviceStatus:
        from devices.zk_client import safe_zk_session
        s = DeviceStatus(
            reachable=self.ping().ok, firmware=self.device.firmware_version,
        )
        # Tentative pull info via SDK
        try:
            with safe_zk_session(ip=self.device.ip_address, port=self._zk_port(),
                                   password=self._zk_password(), timeout=3) as zk:
                if zk is None:
                    return s
                info = self._safe_call(zk, "get_serialnumber")
                s.raw["serial"] = info
                s.raw["users"] = self._safe_call(zk, "get_users_count")
                s.raw["attendances_pending"] = self._safe_call(zk, "get_attendances_count")
        except Exception as exc:
            s.errors.append(f"SDK status KO : {exc}")
        return s

    # ────────────────────────────────────────────────────────────
    # Events pull
    # ────────────────────────────────────────────────────────────
    def read_events(self, since: Optional[datetime] = None) -> Iterable[DeviceEvent]:
        from devices.zk_client import safe_zk_session
        try:
            with safe_zk_session(ip=self.device.ip_address, port=self._zk_port(),
                                   password=self._zk_password(), timeout=3) as zk:
                if zk is None:
                    return []
                atts = zk.pull_attendances(since=since) or []
        except Exception as exc:
            logger.warning("ZK read_events KO %s : %s", self.device.serial_number, exc)
            return []

        events: list[DeviceEvent] = []
        for a in atts:
            events.append(DeviceEvent(
                event_type="rfid.detected",
                at=a.timestamp,
                uid=str(a.user_id),
                granted=True,
                payload={"status": getattr(a, "status", None),
                          "punch":  getattr(a, "punch", None)},
            ))
        return events

    # ────────────────────────────────────────────────────────────
    # Commandes
    # ────────────────────────────────────────────────────────────
    def sync(self) -> DriverResult:
        try:
            from devices.tasks import sync_zkteco_attendances
            sync_zkteco_attendances.delay(device_id=self.device.id)
            return DriverResult(ok=True, detail="task queued")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def restart(self) -> DriverResult:
        # Commande ADMS via cache Redis (récupérée au prochain heartbeat)
        from django.core.cache import cache
        cache.set(f"iclock_cmd:{self.device.serial_number}", "REBOOT_DEV", 300)
        return DriverResult(ok=True, detail="REBOOT_DEV programmé")

    def start_enrollment(self, session_id: str,
                          mode: str = "rfid", timeout_seconds: int = 120) -> DriverResult:
        from django.core.cache import cache
        cache.set(f"iclock_cmd:{self.device.serial_number}", "REG", timeout_seconds)
        return DriverResult(ok=True, detail="mode enrôlement activé",
                             data={"session_id": session_id})

    def stop_enrollment(self, session_id: str) -> DriverResult:
        from django.core.cache import cache
        cache.set(f"iclock_cmd:{self.device.serial_number}", "STOPREG", 60)
        return DriverResult(ok=True)

    def push_user(self, user_data: dict) -> DriverResult:
        """Push un user vers le terminal via pyzk set_user()."""
        from devices.zk_client import safe_zk_session
        try:
            with safe_zk_session(ip=self.device.ip_address, port=self._zk_port(),
                                   password=self._zk_password(), timeout=5) as zk:
                if zk is None:
                    return DriverResult(ok=False, detail="Connexion impossible")
                zk.set_user(
                    uid=int(user_data["uid"]),
                    name=user_data.get("name", "")[:24],
                    privilege=user_data.get("privilege", 0),
                    password=user_data.get("password", ""),
                    group_id=user_data.get("group_id", ""),
                    user_id=str(user_data.get("user_id", user_data["uid"])),
                    card=int(user_data.get("card", 0) or 0),
                )
                return DriverResult(ok=True)
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    # ────────────────────────────────────────────────────────────
    # Helpers privés
    # ────────────────────────────────────────────────────────────
    def _zk_port(self) -> int:
        try:
            return int(self.device.model.spec.get("port", 4370) or 4370)
        except Exception:
            return 4370

    def _zk_password(self) -> int:
        try:
            return int(self.device.model.spec.get("sdk_password", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _safe_call(zk, method_name):
        try:
            return getattr(zk, method_name)()
        except Exception:
            return None
