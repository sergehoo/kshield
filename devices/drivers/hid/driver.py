"""KAYDAN SHIELD — Driver HID Global (VertX / Edge / OMNIKEY).

Interface HTTP simple (VertX EVO expose /webservices/vertx.asmx en SOAP,
Edge Solo expose une API JSON /api/*). Ce driver implémente le sous-ensemble
utile pour Kaydan Shield : ping, info, door_unlock, read_events (SOAP polling).
"""
from __future__ import annotations

import socket
import time
from datetime import datetime
from typing import Iterable, Optional

from ..base import (BaseDriver, Capability, DeviceEvent, DriverResult,
                     register_driver)


@register_driver
class HidDriver(BaseDriver):
    vendor = "hid"
    supported_models = ("VertX", "Edge", "OMNIKEY", "Signo", "iCLASS")
    capabilities = (Capability.PING, Capability.GET_INFO,
                     Capability.READ_EVENTS, Capability.DOOR_UNLOCK)

    def _auth(self):
        from requests.auth import HTTPBasicAuth
        u = self.device.model.spec.get("username", "admin")
        p = self.device.model.spec.get("password", "admin")
        return HTTPBasicAuth(u, p)

    def _base_url(self) -> str:
        proto = "https" if self.device.model.spec.get("tls") else "http"
        return f"{proto}://{self.device.ip_address}"

    def connect(self):    return DriverResult(ok=bool(self.device.ip_address))
    def disconnect(self): return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        t0 = time.perf_counter()
        try:
            with socket.socket() as s:
                s.settimeout(1.5)
                if s.connect_ex((self.device.ip_address, 80)) == 0:
                    return DriverResult(ok=True,
                        data={"latency_ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail="port 80 fermé")

    def read_events(self, since: Optional[datetime] = None) -> Iterable[DeviceEvent]:
        """Polling HID Edge JSON API : GET /api/events?since=…

        Format attendu (Edge) : {"events": [{"time", "card_id", "granted"}, …]}
        Retombe silencieux si l'endpoint n'est pas dispo (device VertX SOAP).
        """
        import requests
        params = {}
        if since:
            params["since"] = since.isoformat()
        try:
            r = requests.get(f"{self._base_url()}/api/events",
                              params=params, auth=self._auth(), timeout=3)
            if not r.ok:
                return []
            data = r.json()
        except Exception:
            return []

        events: list[DeviceEvent] = []
        for e in data.get("events") or []:
            try:
                ts = datetime.fromisoformat(e.get("time"))
            except Exception:
                continue
            events.append(DeviceEvent(
                event_type="rfid.detected", at=ts,
                uid=str(e.get("card_id") or ""),
                granted=bool(e.get("granted")),
                door=str(e.get("door") or ""),
                payload={"raw": e},
            ))
        return events

    def door_unlock(self, door_id: str = "1", duration_seconds: int = 5) -> DriverResult:
        import requests
        try:
            r = requests.post(
                f"{self._base_url()}/api/doors/{door_id}/unlock",
                json={"duration_seconds": duration_seconds},
                auth=self._auth(), timeout=3,
            )
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
