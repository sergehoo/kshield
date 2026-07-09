"""KAYDAN SHIELD — Discovery Orchestrator.

Lance en parallèle tous les probes protocolaires et merge les résultats
par IP/MAC pour éliminer les doublons. Retourne une liste enrichie de
``DiscoveredDevice`` avec ``protocols_detected`` cumulé.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .arp_probe import ArpProbe
from .base import DiscoveredDevice, ProtocolProbe, guess_vendor_from_mac
from .mdns_probe import MdnsProbe
from .onvif_probe import OnvifProbe
from .snmp_probe import SnmpProbe
from .ssdp_probe import SsdpProbe

logger = logging.getLogger(__name__)


PROTOCOL_CLASSES: dict[str, type[ProtocolProbe]] = {
    "onvif": OnvifProbe,
    "mdns":  MdnsProbe,
    "ssdp":  SsdpProbe,
    "arp":   ArpProbe,
    "snmp":  SnmpProbe,
}


class DiscoveryOrchestrator:
    """Combine plusieurs probes en parallèle."""

    def __init__(self, protocols: Optional[list[str]] = None,
                  timeout: float = 4.0):
        self.protocols = protocols or list(PROTOCOL_CLASSES.keys())
        self.timeout = timeout

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        probes = []
        for p in self.protocols:
            cls = PROTOCOL_CLASSES.get(p)
            if cls is not None:
                probes.append(cls(timeout=self.timeout))

        results: list[DiscoveredDevice] = []
        with ThreadPoolExecutor(max_workers=len(probes) or 1) as pool:
            futures = {pool.submit(_safe_scan, p, ip_range): p for p in probes}
            for fut in as_completed(futures):
                probe = futures[fut]
                try:
                    devices = fut.result()
                    logger.info("Discovery %s : %d équipements", probe.name, len(devices))
                    results.extend(devices)
                except Exception as exc:
                    logger.warning("Probe %s a échoué : %s", probe.name, exc)

        merged = _merge_by_ip(results)
        _mark_already_known(merged)
        return merged


def _safe_scan(probe: ProtocolProbe, ip_range):
    return probe.scan(ip_range)


def _merge_by_ip(devices: list[DiscoveredDevice]) -> list[DiscoveredDevice]:
    """Merge plusieurs découvertes de la même IP (par différents protocoles)."""
    by_ip: dict[str, DiscoveredDevice] = {}
    for d in devices:
        if not d.ip:
            continue
        prev = by_ip.get(d.ip)
        if prev is None:
            by_ip[d.ip] = d
            continue
        # Merge
        prev.mac = prev.mac or d.mac
        prev.hostname = prev.hostname or d.hostname
        prev.vendor = prev.vendor or d.vendor
        prev.model = prev.model or d.model
        prev.firmware = prev.firmware or d.firmware
        prev.open_ports = sorted(set(prev.open_ports + d.open_ports))
        prev.protocols_detected = sorted(set(
            prev.protocols_detected + d.protocols_detected))
        prev.device_type_hint = prev.device_type_hint or d.device_type_hint
        for k, v in d.protocols_raw.items():
            if k in prev.protocols_raw:
                if isinstance(prev.protocols_raw[k], list):
                    prev.protocols_raw[k].extend(
                        v if isinstance(v, list) else [v])
                else:
                    prev.protocols_raw[k] = [prev.protocols_raw[k], v]
            else:
                prev.protocols_raw[k] = v

    # Second pass — infère vendor via MAC si toujours vide
    for d in by_ip.values():
        if not d.vendor and d.mac:
            d.vendor = guess_vendor_from_mac(d.mac)
    return list(by_ip.values())


def _mark_already_known(devices: list[DiscoveredDevice]):
    """Marque les IPs déjà présentes en base."""
    try:
        from devices.models import Device
        ips = [d.ip for d in devices if d.ip]
        known = set(Device.objects.filter(ip_address__in=ips)
                                    .values_list("ip_address", flat=True))
        for d in devices:
            if d.ip in known:
                d.already_known = True
    except Exception as exc:
        logger.debug("_mark_already_known KO : %s", exc)
