"""KAYDAN SHIELD — Discovery ONVIF WS-Discovery.

Utilise ``wsdiscovery`` (probe UDP 3702). Retourne toutes les caméras et
lecteurs ONVIF présents sur le LAN.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .base import DiscoveredDevice, ProtocolProbe

logger = logging.getLogger(__name__)


class OnvifProbe(ProtocolProbe):
    name = "onvif"

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        try:
            from wsdiscovery.discovery import ThreadedWSDiscovery
        except ImportError:
            logger.info("wsdiscovery non installé — skip ONVIF discovery")
            return []

        wsd = ThreadedWSDiscovery()
        found: list[DiscoveredDevice] = []
        try:
            wsd.start()
            services = wsd.searchServices(timeout=int(self.timeout))
            for svc in services:
                xaddrs = list(svc.getXAddrs())
                if not xaddrs:
                    continue
                ip = _extract_ip(xaddrs[0])
                if not ip:
                    continue
                types = " ".join(str(t) for t in svc.getTypes())
                scopes = " ".join(str(s) for s in svc.getScopes())

                d = DiscoveredDevice(
                    ip=ip, protocols_detected=["onvif"],
                    device_type_hint=_detect_hint(types + " " + scopes),
                )
                d.protocols_raw["onvif"] = {
                    "types": types, "scopes": scopes, "xaddrs": xaddrs,
                }
                # Guess vendor via scopes
                d.vendor = _guess_from_scopes(scopes) or d.vendor
                found.append(d)
        except Exception as exc:
            logger.warning("ONVIF discovery KO : %s", exc)
        finally:
            try:
                wsd.stop()
            except Exception:
                pass
        return found


def _extract_ip(xaddr: str) -> str:
    m = re.search(r"//([\d.]+)", xaddr or "")
    return m.group(1) if m else ""


def _detect_hint(text: str) -> str:
    t = (text or "").lower()
    if "camera" in t or "video" in t: return "camera"
    if "door" in t or "access" in t: return "door_lock"
    return ""


def _guess_from_scopes(scopes: str) -> str:
    s = (scopes or "").lower()
    for vendor in ("hikvision", "dahua", "axis", "bosch", "vivotek", "hanwha",
                    "sony", "panasonic", "avigilon", "uniview"):
        if vendor in s:
            return vendor
    return ""
