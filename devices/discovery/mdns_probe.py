"""KAYDAN SHIELD — Discovery mDNS / Bonjour (zeroconf)."""
from __future__ import annotations

import logging
import socket
import time
from typing import Optional

from .base import DiscoveredDevice, ProtocolProbe

logger = logging.getLogger(__name__)

# Services mDNS typiques du monde sécurité / IoT
MDNS_SERVICES = [
    "_axis-video._tcp.local.",   # Axis
    "_hap._tcp.local.",           # HomeKit (Apple)
    "_workstation._tcp.local.",   # SMB / Windows
    "_ipp._tcp.local.",           # imprimantes / TB
    "_http._tcp.local.",          # web UI génériques
    "_rtsp._tcp.local.",          # caméras RTSP
    "_onvif._tcp.local.",         # ONVIF sur mDNS (rare)
]


class MdnsProbe(ProtocolProbe):
    name = "mdns"

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
        except ImportError:
            logger.info("zeroconf non installé — skip mDNS discovery")
            return []

        found: dict[str, DiscoveredDevice] = {}

        class _Listener(ServiceListener):
            def add_service(self, zc, type_, name):
                try:
                    info = zc.get_service_info(type_, name, timeout=1500)
                    if info is None: return
                    for a in info.parsed_addresses():
                        try:
                            ip = str(a)
                            d = found.get(ip) or DiscoveredDevice(ip=ip)
                            d.hostname = info.server.rstrip(".") if info.server else d.hostname
                            if "mdns" not in d.protocols_detected:
                                d.protocols_detected.append("mdns")
                            d.protocols_raw.setdefault("mdns", []).append({
                                "type": type_, "name": name,
                                "properties": {k.decode() if isinstance(k, bytes) else k:
                                                 v.decode(errors="replace") if isinstance(v, bytes) else v
                                                 for k, v in (info.properties or {}).items()},
                            })
                            found[ip] = d
                        except Exception:
                            continue
                except Exception:
                    pass

            def remove_service(self, *a, **kw): pass
            def update_service(self, *a, **kw): pass

        zc = Zeroconf()
        try:
            listener = _Listener()
            for svc in MDNS_SERVICES:
                try:
                    ServiceBrowser(zc, svc, listener)
                except Exception:
                    continue
            time.sleep(self.timeout)
        finally:
            try:
                zc.close()
            except Exception:
                pass
        return list(found.values())
