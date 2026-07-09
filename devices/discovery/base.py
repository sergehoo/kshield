"""KAYDAN SHIELD — Auto Discovery, contrat commun.

Chaque protocole (ONVIF, mDNS, SSDP, SNMP, ARP, TCP) est isolé dans un module
qui implémente ``ProtocolProbe.scan()`` → liste de ``DiscoveredDevice``.

L'orchestrateur ``DiscoveryOrchestrator`` combine tous les probes en parallèle
et merge les résultats par IP/MAC pour éviter les doublons.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DiscoveredDevice:
    """Candidat détecté sur le réseau — normalisé, indépendant du protocole."""
    ip: str
    mac: str = ""
    hostname: str = ""
    vendor: str = ""              # inféré (Hikvision, ZKTeco…)
    model: str = ""
    firmware: str = ""
    open_ports: list[int] = field(default_factory=list)
    protocols_detected: list[str] = field(default_factory=list)
    device_type_hint: str = ""    # face_terminal / camera / reader_uhf / …
    already_known: bool = False   # Device existe déjà en base pour cette IP
    raw: dict = field(default_factory=dict)
    protocols_raw: dict = field(default_factory=dict)  # payload par protocole
    detected_at: datetime = field(default_factory=datetime.utcnow)


class ProtocolProbe(abc.ABC):
    """Chaque protocole implémente cette classe."""
    name: str = "base"

    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout

    @abc.abstractmethod
    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        """Retourne la liste des équipements détectés.

        Args:
            ip_range: si le protocole permet un scan ciblé (ex. ARP, TCP), on
                lui passe la liste d'IPs. Sinon (mDNS, SSDP, ONVIF WS-Discovery),
                le protocole écoute passivement le réseau local.
        """


# ═══════════════════════════════════════════════════════════════════
# Fingerprinting — devine le constructeur à partir de la MAC (OUI)
# ═══════════════════════════════════════════════════════════════════
MAC_OUI_VENDORS = {
    # ZKTeco
    "0021ce": "zkteco", "02fb27": "zkteco",
    # Hikvision
    "44192b": "hikvision", "c04e5f": "hikvision", "10184c": "hikvision",
    "8830f0": "hikvision", "58032b": "hikvision", "b06e19": "hikvision",
    # Dahua
    "3c2a4a": "dahua", "9c8ecd": "dahua", "d02788": "dahua",
    # Axis
    "00408c": "axis", "acdd67": "axis", "b8a44f": "axis",
    # Suprema
    "00179a": "suprema", "0016b1": "suprema",
    # HID
    "00060e": "hid", "0006ee": "hid",
    # Bosch
    "00b41a": "bosch", "b8d70d": "bosch",
    # Raspberry Pi
    "b827eb": "raspberry_pi", "dca632": "raspberry_pi", "e45f01": "raspberry_pi",
}


def guess_vendor_from_mac(mac: str) -> str:
    """Devine le vendor via l'OUI (3 premiers octets)."""
    if not mac:
        return ""
    mac = mac.lower().replace(":", "").replace("-", "").replace(".", "")
    if len(mac) < 6:
        return ""
    return MAC_OUI_VENDORS.get(mac[:6], "")
