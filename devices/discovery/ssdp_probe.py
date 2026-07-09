"""KAYDAN SHIELD — Discovery SSDP / UPnP (M-SEARCH multicast 239.255.255.250:1900)."""
from __future__ import annotations

import logging
import re
import socket
import time
from typing import Optional

from .base import DiscoveredDevice, ProtocolProbe

logger = logging.getLogger(__name__)

MSEARCH_MSG = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: ssdp:all\r\n"
    "\r\n"
).encode()


class SsdpProbe(ProtocolProbe):
    name = "ssdp"

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        found: dict[str, DiscoveredDevice] = {}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                   socket.IPPROTO_UDP)
            sock.settimeout(self.timeout)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.sendto(MSEARCH_MSG, ("239.255.255.250", 1900))
            end = time.time() + self.timeout
            while time.time() < end:
                try:
                    data, (ip, _port) = sock.recvfrom(4096)
                except socket.timeout:
                    break
                text = data.decode(errors="replace")
                d = found.get(ip) or DiscoveredDevice(ip=ip)
                d.protocols_detected = list(set(d.protocols_detected + ["ssdp"]))
                # Parse headers
                headers = _parse_headers(text)
                d.protocols_raw.setdefault("ssdp", []).append(headers)
                # Server hint
                srv = headers.get("server", "")
                for vendor in ("hikvision", "dahua", "axis", "sony", "onvif",
                                "camera", "zkteco"):
                    if vendor in srv.lower():
                        d.vendor = vendor
                        break
                found[ip] = d
        except Exception as exc:
            logger.warning("SSDP scan KO : %s", exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass
        return list(found.values())


def _parse_headers(text: str) -> dict:
    out = {}
    for line in text.split("\r\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out
