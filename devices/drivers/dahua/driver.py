"""KAYDAN SHIELD — Driver Dahua (CGI + Public SDK).

Utilise l'API CGI Dahua (/cgi-bin/…) proche d'Hikvision mais avec auth Basic
et retour multiline plain-text (pas XML). Endpoints clés :
    /cgi-bin/magicBox.cgi?action=getSystemInfo
    /cgi-bin/accessControl.cgi?action=openDoor&channel=1
    /cgi-bin/recordFinder.cgi?action=find&name=AccessControlCardRec&…
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, Optional

from ..base import (BaseDriver, Capability, DeviceEvent, DeviceInfo,
                     DriverResult, register_driver)


@register_driver
class DahuaDriver(BaseDriver):
    vendor = "dahua"
    supported_models = ("IPC-", "DHI-", "DH-", "TPC-", "SD", "ASI", "ASA")
    capabilities = (Capability.PING, Capability.GET_INFO, Capability.GET_STATUS,
                     Capability.READ_EVENTS, Capability.RESTART,
                     Capability.DOOR_UNLOCK)

    def _auth(self):
        from requests.auth import HTTPBasicAuth
        u = self.device.model.spec.get("username", "admin")
        p = self.device.model.spec.get("password", "admin")
        return HTTPBasicAuth(u, p)

    def _url(self, path: str) -> str:
        proto = "https" if self.device.model.spec.get("tls") else "http"
        return f"{proto}://{self.device.ip_address}{path}"

    def connect(self):    return DriverResult(ok=bool(self.device.ip_address))
    def disconnect(self): return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        import requests
        t0 = time.perf_counter()
        try:
            r = requests.get(self._url("/cgi-bin/magicBox.cgi?action=getSystemInfo"),
                              auth=self._auth(), timeout=2)
            if r.status_code < 500:
                return DriverResult(ok=True,
                    data={"latency_ms": int((time.perf_counter() - t0) * 1000),
                           "http_status": r.status_code})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))
        return DriverResult(ok=False, detail="CGI muet")

    def restart(self) -> DriverResult:
        import requests
        try:
            r = requests.get(self._url("/cgi-bin/magicBox.cgi?action=reboot"),
                              auth=self._auth(), timeout=3)
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def door_unlock(self, door_id: str = "1", duration_seconds: int = 5) -> DriverResult:
        import requests
        try:
            r = requests.get(
                self._url(f"/cgi-bin/accessControl.cgi?"
                            f"action=openDoor&channel={door_id}&"
                            f"UserID=kshield&Type=Remote"),
                auth=self._auth(), timeout=3,
            )
            return DriverResult(ok=r.ok, detail=f"HTTP {r.status_code}")
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def read_events(self, since=None):
        """Récupère les derniers Access Control Card Records via recordFinder."""
        import requests
        params = {
            "action": "find",
            "name": "AccessControlCardRec",
            "count": 100,
        }
        if since:
            params["StartTime"] = since.strftime("%Y-%m-%d %H:%M:%S")
        try:
            r = requests.get(self._url("/cgi-bin/recordFinder.cgi"),
                              params=params, auth=self._auth(), timeout=4)
            if not r.ok:
                return []
        except Exception:
            return []

        events = []
        # Format Dahua : lignes clef=valeur, un enregistrement par bloc
        current = {}
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                if current:
                    ev = self._parse_ac_record(current)
                    if ev:
                        events.append(ev)
                    current = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
        if current:
            ev = self._parse_ac_record(current)
            if ev:
                events.append(ev)
        return events

    def _parse_ac_record(self, rec: dict):
        try:
            ts = datetime.strptime(rec.get("CreateTime", ""), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
        return DeviceEvent(
            event_type="rfid.detected", at=ts,
            uid=str(rec.get("CardNo") or rec.get("UserID") or ""),
            granted=(rec.get("Status") in ("1", "OK", "Success")),
            door=str(rec.get("ReaderID") or ""),
            payload={"raw": rec},
        )
