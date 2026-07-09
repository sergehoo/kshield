"""KAYDAN SHIELD — Driver Axis (VAPIX API)."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, Optional

from ..base import (BaseDriver, Capability, DeviceEvent, DriverResult,
                     register_driver)


@register_driver
class AxisDriver(BaseDriver):
    vendor = "axis"
    supported_models = ("A1001", "A9161", "P32", "P33", "M30", "Q60", "Q35",
                         "AXIS")
    capabilities = (Capability.PING, Capability.GET_INFO, Capability.READ_EVENTS,
                     Capability.RESTART, Capability.DOOR_UNLOCK)

    def _auth(self):
        from requests.auth import HTTPDigestAuth
        u = self.device.model.spec.get("username", "root")
        p = self.device.model.spec.get("password", "root")
        return HTTPDigestAuth(u, p)

    def _url(self, path: str) -> str:
        proto = "https" if self.device.model.spec.get("tls") else "http"
        return f"{proto}://{self.device.ip_address}{path}"

    def connect(self):    return DriverResult(ok=bool(self.device.ip_address))
    def disconnect(self): return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        import requests
        t0 = time.perf_counter()
        try:
            r = requests.get(self._url("/axis-cgi/param.cgi?action=list&group=Brand"),
                              auth=self._auth(), timeout=2)
            if r.status_code < 500:
                return DriverResult(ok=True,
                    data={"latency_ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail="VAPIX muet")

    def restart(self) -> DriverResult:
        import requests
        try:
            r = requests.get(self._url("/axis-cgi/restart.cgi"),
                              auth=self._auth(), timeout=3)
            return DriverResult(ok=r.ok)
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def door_unlock(self, door_id: str = "1", duration_seconds: int = 5) -> DriverResult:
        """Axis A1001/A9161 : /vapix/services (SOAP) OU /VAPIX/AccessControl/…"""
        import requests
        try:
            r = requests.get(
                self._url(
                    "/axis-cgi/access/door.cgi?action=access"
                    f"&doorToken={door_id}&duration={duration_seconds}",
                ),
                auth=self._auth(), timeout=3,
            )
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def read_events(self, since: Optional[datetime] = None) -> Iterable[DeviceEvent]:
        """VAPIX Event Log : /axis-cgi/eventlog/entrylog.cgi

        Retourne les événements ACAP au format ligne : timestamp;source;event
        """
        import requests
        try:
            r = requests.get(
                self._url("/axis-cgi/eventlog/entrylog.cgi?nbrofentries=200"),
                auth=self._auth(), timeout=3,
            )
            if not r.ok:
                return []
        except Exception:
            return []
        events: list[DeviceEvent] = []
        for line in r.text.splitlines():
            # Format simplifié — Axis retourne du texte structuré
            if "AccessGranted" not in line and "AccessDenied" not in line:
                continue
            parts = line.split(";")
            if len(parts) < 3:
                continue
            try:
                ts = datetime.fromisoformat(parts[0].strip())
            except Exception:
                continue
            events.append(DeviceEvent(
                event_type="rfid.detected", at=ts,
                uid=parts[2].strip() if len(parts) > 2 else "",
                granted="AccessGranted" in line,
                payload={"raw": line},
            ))
        return events
