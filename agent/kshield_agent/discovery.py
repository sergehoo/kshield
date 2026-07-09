"""Kaydan Edge Gateway — auto-discovery embarqué.

Version légère et purement stdlib : ARP + ICMP ping + probe TCP sur ports
communs. Pas de deps sur wsdiscovery/zeroconf/pysnmp (l'agent doit rester
léger — l'admin peut activer les probes optionnels par config).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import platform
import re
import socket
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


COMMON_PORTS = {
    80:   "http",
    443:  "https",
    22:   "ssh",
    554:  "rtsp",
    4370: "zkteco",
    5084: "llrp",
    3702: "onvif",
    8080: "http-alt",
    8000: "api",
}


async def scan_local_network(timeout_per_ip: float = 0.5,
                              max_ips: int = 254) -> list[dict]:
    """Scanne le sous-réseau /24 local et retourne la liste des devices détectés.

    Args:
        timeout_per_ip: timeout TCP par port (défaut 500ms).
        max_ips: nombre max d'IP à sonder (défaut 254 → toute la /24).

    Returns:
        Liste de dicts ``{ip, mac, hostname, open_ports, protocol_hints}``.
    """
    local_ip = _detect_local_ip()
    if not local_ip:
        logger.warning("Impossible de détecter l'IP locale — skip scan")
        return []

    # Déduit le sous-réseau /24
    try:
        net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError as exc:
        logger.warning("Sous-réseau invalide : %s", exc)
        return []

    arp_table = _read_arp_table()
    logger.info("Scan agent : sous-réseau %s (%d IPs)", net, min(net.num_addresses, max_ips))

    ips = [str(ip) for ip in net.hosts()][:max_ips]

    # Sonde les IPs en parallèle
    tasks = [asyncio.create_task(_probe_ip(ip, arp_table, timeout_per_ip))
              for ip in ips]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    found = []
    for r in results:
        if isinstance(r, dict) and r.get("ip"):
            found.append(r)
    logger.info("Scan agent terminé : %d/%d IPs répondent", len(found), len(ips))
    return found


async def _probe_ip(ip: str, arp_table: dict, timeout: float) -> Optional[dict]:
    """Sonde une IP : d'abord ARP (déjà connue ?), puis TCP sur ports courants."""
    mac = arp_table.get(ip)

    # Probe TCP parallèle sur ports communs
    ports_open: list[int] = []
    protocol_hints: list[str] = []

    async def _try_port(p: int):
        try:
            fut = asyncio.open_connection(ip, p)
            _reader, writer = await asyncio.wait_for(fut, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return p
        except Exception:
            return None

    tasks = [_try_port(p) for p in COMMON_PORTS]
    for r in await asyncio.gather(*tasks):
        if r:
            ports_open.append(r)
            hint = COMMON_PORTS.get(r)
            if hint:
                protocol_hints.append(hint)

    if not ports_open and not mac:
        return None    # ni MAC connue ni port ouvert → skip

    # Hostname reverse
    hostname = ""
    try:
        hostname = socket.getfqdn(ip)
        if hostname == ip:
            hostname = ""
    except Exception:
        pass

    return {
        "ip": ip, "mac": mac or "", "hostname": hostname,
        "open_ports": ports_open,
        "protocol_hints": sorted(set(protocol_hints)),
    }


def _detect_local_ip() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def _read_arp_table() -> dict[str, str]:
    """Lit la table ARP OS. Retourne {ip: mac}."""
    table: dict[str, str] = {}
    system = platform.system()

    # Linux : /proc/net/arp
    if system == "Linux":
        try:
            with open("/proc/net/arp") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip, _, _, mac = parts[0], parts[1], parts[2], parts[3]
                        if mac != "00:00:00:00:00:00":
                            table[ip] = mac
            return table
        except Exception:
            pass

    # macOS / Windows / BSD : parser la sortie de `arp -a`
    try:
        out = subprocess.check_output(["arp", "-a"], timeout=3,
                                        stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            m = re.search(r"\(?(\d+\.\d+\.\d+\.\d+)\)?.*?([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})",
                            line)
            if m:
                table[m.group(1)] = m.group(2).lower().replace("-", ":")
    except Exception as exc:
        logger.debug("arp -a KO : %s", exc)

    return table
