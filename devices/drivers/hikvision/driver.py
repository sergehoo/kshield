"""KAYDAN SHIELD — Driver Hikvision (ISAPI HTTP).

Utilise l'API ISAPI (Intelligent Security API) commune à toutes les gammes
Hikvision : caméras IP, terminaux d'accès, portiques, sonneries de porte.

Endpoints clefs :
    GET /ISAPI/System/deviceInfo
    GET /ISAPI/System/status
    PUT /ISAPI/AccessControl/RemoteControl/door/1  (unlock)
    POST /ISAPI/AccessControl/CardInfo/Record?format=json  (enroll RFID)

Auth : Digest ou Basic selon firmware.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..base import (BaseDriver, Capability, DeviceInfo, DeviceStatus, DriverResult,
                     register_driver)

logger = logging.getLogger(__name__)


@register_driver
class HikvisionDriver(BaseDriver):
    """Driver Hikvision — caméras IP + terminaux d'accès (ISAPI)."""

    vendor = "hikvision"
    supported_models = ("DS-", "iVMS", "DS-K", "DS-2", "DS-3")
    capabilities = (
        Capability.PING, Capability.GET_INFO, Capability.GET_STATUS,
        Capability.DOOR_UNLOCK, Capability.ENROLL_RFID, Capability.RESTART,
    )

    def _auth(self):
        """Retourne un objet requests.auth compatible (Digest préféré)."""
        try:
            from requests.auth import HTTPDigestAuth
            u = self.device.model.spec.get("username", "admin")
            p = self.device.model.spec.get("password", "12345")
            return HTTPDigestAuth(u, p)
        except Exception:
            return None

    def _url(self, path: str) -> str:
        proto = "https" if self.device.model.spec.get("tls") else "http"
        return f"{proto}://{self.device.ip_address}{path}"

    # ────────────────────────────────────────────────────────────
    def connect(self) -> DriverResult:
        return DriverResult(ok=bool(self.device.ip_address))

    def disconnect(self) -> DriverResult:
        return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        import requests
        t0 = time.perf_counter()
        try:
            r = requests.get(self._url("/ISAPI/System/deviceInfo"),
                              auth=self._auth(), timeout=2)
            if r.status_code < 500:
                return DriverResult(ok=True, detail="ISAPI répond",
                                     data={"latency_ms": int((time.perf_counter() - t0) * 1000),
                                            "http_status": r.status_code})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail="pas de réponse ISAPI")

    def get_info(self) -> DeviceInfo:
        import requests
        info = super().get_info()
        try:
            r = requests.get(self._url("/ISAPI/System/deviceInfo"),
                              auth=self._auth(), timeout=3)
            if r.ok:
                # Parse XML minimal (sans lxml pour éviter la dep)
                import re
                text = r.text
                for tag in ("serialNumber", "firmwareVersion", "hardwareVersion",
                            "model", "deviceName"):
                    m = re.search(f"<{tag}>(.*?)</{tag}>", text)
                    if m:
                        info.raw[tag] = m.group(1)
                info.serial = info.raw.get("serialNumber") or info.serial
                info.firmware = info.raw.get("firmwareVersion") or info.firmware
                info.hardware = info.raw.get("hardwareVersion") or info.hardware
                info.model = info.raw.get("model") or info.model
        except Exception as exc:
            logger.debug("Hik get_info KO : %s", exc)
        return info

    def get_status(self) -> DeviceStatus:
        s = DeviceStatus(reachable=self.ping().ok, firmware=self.device.firmware_version)
        import requests
        try:
            r = requests.get(self._url("/ISAPI/System/status"),
                              auth=self._auth(), timeout=3)
            if r.ok:
                import re
                text = r.text
                for k, tag in (("uptime_seconds", "deviceUpTime"),
                                ("cpu_percent", "CPULoad"),
                                ("ram_percent", "MemoryUsage")):
                    m = re.search(f"<{tag}>(.*?)</{tag}>", text)
                    if m:
                        try:
                            setattr(s, k, float(m.group(1)))
                        except ValueError:
                            pass
        except Exception as exc:
            s.errors.append(str(exc))
        return s

    def door_unlock(self, door_id: str = "1", duration_seconds: int = 5) -> DriverResult:
        import requests
        payload = {"RemoteControlDoor": {"cmd": "open"}}
        try:
            r = requests.put(self._url(f"/ISAPI/AccessControl/RemoteControl/door/{door_id}"),
                              json=payload, auth=self._auth(), timeout=3)
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def restart(self) -> DriverResult:
        import requests
        try:
            r = requests.put(self._url("/ISAPI/System/reboot"),
                              auth=self._auth(), timeout=3)
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
