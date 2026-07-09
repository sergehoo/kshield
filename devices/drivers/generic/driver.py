"""KAYDAN SHIELD — Driver générique (fallback).

Utilisé quand aucun driver vendor-specific ne match. Fait uniquement le
minimum viable : ping TCP + get_info depuis les champs BDD.
"""
from __future__ import annotations

import socket
import time

from ..base import BaseDriver, Capability, DriverResult, register_driver


@register_driver
class GenericDriver(BaseDriver):
    vendor = "generic"
    supported_models = ()   # fallback ultime
    capabilities = (Capability.PING, Capability.GET_INFO)

    def connect(self):    return DriverResult(ok=True)
    def disconnect(self): return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        if not self.device.ip_address:
            return DriverResult(ok=False, detail="Pas d'IP")
        ports_to_try = [80, 443, 8080, 22, 4370, 5084, 554]
        for port in ports_to_try:
            t0 = time.perf_counter()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    if s.connect_ex((self.device.ip_address, port)) == 0:
                        return DriverResult(ok=True, detail=f"port {port}",
                            data={"port": port,
                                   "latency_ms": int((time.perf_counter() - t0) * 1000)})
            except Exception:
                continue
        return DriverResult(ok=False, detail="aucun port ouvert")
