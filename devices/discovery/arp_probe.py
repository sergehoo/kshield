"""KAYDAN SHIELD — Discovery ARP (lecture table /proc/net/arp sous Linux).

Retourne toutes les entrées ARP actives = équipements qui ont récemment
communiqué sur le LAN. Complémentaire au scan TCP : ne nécessite pas
d'ouvrir de ports.
"""
from __future__ import annotations

import logging
from typing import Optional

from .base import DiscoveredDevice, ProtocolProbe, guess_vendor_from_mac

logger = logging.getLogger(__name__)


class ArpProbe(ProtocolProbe):
    name = "arp"

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        try:
            with open("/proc/net/arp") as f:
                lines = f.readlines()[1:]
        except FileNotFoundError:
            logger.info("/proc/net/arp indisponible (non-Linux) — skip ARP")
            return []
        except Exception as exc:
            logger.warning("ARP probe KO : %s", exc)
            return []

        out: list[DiscoveredDevice] = []
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            ip, hw_type, flags, mac = parts[0], parts[1], parts[2], parts[3]
            if mac == "00:00:00:00:00:00":
                continue
            if ip_range is not None and ip not in ip_range:
                continue
            d = DiscoveredDevice(
                ip=ip, mac=mac, protocols_detected=["arp"],
                vendor=guess_vendor_from_mac(mac),
            )
            d.protocols_raw["arp"] = {"hw_type": hw_type, "flags": flags}
            out.append(d)
        return out
