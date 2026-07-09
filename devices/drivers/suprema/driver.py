"""KAYDAN SHIELD — Driver Suprema BioStar 2 (REST API).

Suprema expose une API REST BioStar 2 pour piloter les terminaux BioStation,
FaceStation, BioLite. L'auth se fait par bearer token obtenu via /api/login.

Endpoints clefs :
    POST /api/login                            → {user_id, password} → token
    GET  /api/devices/{id}
    GET  /api/devices/{id}/status
    POST /api/devices/{id}/reboot
    POST /api/access/enrollment/start
"""
from __future__ import annotations

import logging

from ..base import (BaseDriver, Capability, DeviceInfo, DeviceStatus, DriverResult,
                     register_driver)

logger = logging.getLogger(__name__)


@register_driver
class SupremaDriver(BaseDriver):
    """Driver Suprema BioStar 2 (REST + WebSocket)."""

    vendor = "suprema"
    supported_models = ("BioStation", "FaceStation", "BioLite", "BioEntry", "X-Station")
    capabilities = (
        Capability.PING, Capability.GET_INFO, Capability.GET_STATUS,
        Capability.ENROLL_RFID, Capability.ENROLL_FACE, Capability.ENROLL_FINGERPRINT,
        Capability.RESTART, Capability.PUSH_USER,
    )

    def _url(self, path: str) -> str:
        proto = "https" if self.device.model.spec.get("tls", True) else "http"
        port = self.device.model.spec.get("api_port", 443)
        return f"{proto}://{self.device.ip_address}:{port}{path}"

    def _get_token(self):
        """Login et récupère le token BioStar 2."""
        import requests
        try:
            r = requests.post(self._url("/api/login"), json={
                "User": {
                    "login_id": self.device.model.spec.get("username", "admin"),
                    "password": self.device.model.spec.get("password", "admin"),
                },
            }, timeout=5, verify=False)
            if r.ok:
                return r.headers.get("bs-session-id")
        except Exception as exc:
            logger.debug("Suprema login KO : %s", exc)
        return None

    def connect(self) -> DriverResult:
        token = self._get_token()
        if not token:
            return DriverResult(ok=False, detail="login KO")
        self._token = token
        return DriverResult(ok=True)

    def disconnect(self) -> DriverResult:
        return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        import socket, time
        if not self.device.ip_address:
            return DriverResult(ok=False, detail="Pas d'IP")
        t0 = time.perf_counter()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                port = self.device.model.spec.get("api_port", 443)
                if s.connect_ex((self.device.ip_address, port)) == 0:
                    return DriverResult(ok=True, detail="reachable",
                                         data={"latency_ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail="port fermé")

    def get_status(self) -> DeviceStatus:
        s = DeviceStatus(reachable=self.ping().ok, firmware=self.device.firmware_version)
        # BioStar 2 : GET /api/devices/{id}/status
        return s

    def restart(self) -> DriverResult:
        return self._device_action("reboot")

    def door_unlock(self, door_id: str = "", duration_seconds: int = 5) -> DriverResult:
        """POST /api/doors/{id}/open — BioStar 2 pilote directement les portes."""
        import requests
        token = getattr(self, "_token", None) or self._get_token()
        if not token:
            return DriverResult(ok=False, detail="pas de token")
        door = door_id or self.device.model.spec.get("door_id", "1")
        try:
            r = requests.post(
                self._url(f"/api/doors/{door}/open"),
                headers={"bs-session-id": token},
                timeout=5, verify=False,
            )
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def read_events(self, since=None):
        """GET /api/events/search — BioStar 2 renvoie l'historique en JSON."""
        from datetime import datetime
        from ..base import DeviceEvent
        import requests
        token = getattr(self, "_token", None) or self._get_token()
        if not token:
            return []
        params = {"limit": 100}
        if since:
            params["startDateTime"] = since.isoformat()
        try:
            r = requests.get(
                self._url("/api/events/search"),
                headers={"bs-session-id": token},
                params=params, timeout=5, verify=False,
            )
            if not r.ok:
                return []
            data = r.json()
        except Exception:
            return []

        events = []
        for e in (data.get("Event") or data.get("EventCollection", {}).get("rows") or []):
            try:
                ts = datetime.fromisoformat(e.get("datetime") or e.get("dateTime"))
            except Exception:
                continue
            events.append(DeviceEvent(
                event_type="rfid.detected", at=ts,
                uid=str(e.get("card_id") or e.get("userID") or ""),
                granted=(e.get("code") in (1, "1", "AC_OK")),
                door=str(e.get("device_id") or e.get("deviceID") or ""),
                payload={"raw": e},
            ))
        return events

    def push_user(self, user_data: dict) -> DriverResult:
        """POST /api/users — crée/update un user via BioStar 2 REST."""
        import requests
        token = getattr(self, "_token", None) or self._get_token()
        if not token:
            return DriverResult(ok=False, detail="pas de token")
        payload = {
            "User": {
                "user_id": str(user_data.get("user_id") or user_data.get("uid")),
                "name":    user_data.get("name", "")[:48],
                "cards":   [{"card_id": str(user_data["card"])}] if user_data.get("card") else [],
            }
        }
        try:
            r = requests.post(self._url("/api/users"),
                                json=payload,
                                headers={"bs-session-id": token,
                                          "Content-Type": "application/json"},
                                timeout=5, verify=False)
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def _device_action(self, action: str) -> DriverResult:
        import requests
        token = getattr(self, "_token", None) or self._get_token()
        if not token:
            return DriverResult(ok=False, detail="pas de token")
        try:
            device_biostar_id = self.device.model.spec.get("biostar_id", "")
            r = requests.post(
                self._url(f"/api/devices/{device_biostar_id}/{action}"),
                headers={"bs-session-id": token}, timeout=5, verify=False,
            )
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
