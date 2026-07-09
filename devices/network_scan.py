"""KAYDAN SHIELD — Module de scan réseau non destructif.

Détecte les équipements sur une plage IP via TCP probes parallèles.
- Progression et résultats stockés en cache Redis (TTL 1h)
- Thread background lance le scan sans bloquer la request HTTP
- Détection heuristique de protocole selon les ports ouverts :
    port 4370  → ZKTeco (biométrie)
    port 5084  → LLRP (portique UHF)
    port 554   → RTSP (caméra)
    port 3702  → ONVIF WS-Discovery
    port 80/8080 → HTTP (générique, souvent webUI)
    port 443    → HTTPS
    port 22     → SSH (gateway Linux)
    port 8000   → API custom
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Ports par défaut à sonder — équipements Kaydan Shield
DEFAULT_PORTS = [80, 443, 4370, 5084, 554, 3702, 8000, 8080, 22]

# Mapping port → protocole probable + type d'équipement
PORT_HINTS = {
    4370: ("ZKTeco / ADMS", "face_terminal"),
    5084: ("LLRP UHF", "portique"),
    554:  ("RTSP", "camera"),
    3702: ("ONVIF", "camera"),
    22:   ("SSH", "gateway"),
    8000: ("API générique", None),
    80:   ("HTTP", None),
    443:  ("HTTPS", None),
    8080: ("HTTP alt", None),
}

TIMEOUT_S = 0.5   # timeout TCP probe court
MAX_WORKERS = 32  # scan parallèle


def _cache_key(scan_id: str) -> str:
    return f"network_scan:{scan_id}"


def _update(scan_id: str, **fields):
    """Met à jour l'état du scan dans le cache."""
    state = cache.get(_cache_key(scan_id)) or {}
    state.update(fields)
    cache.set(_cache_key(scan_id), state, 3600)


def _append_log(scan_id: str, msg: str):
    state = cache.get(_cache_key(scan_id)) or {}
    logs = state.get("logs") or []
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    state["logs"] = logs[-200:]  # cap 200 lignes
    cache.set(_cache_key(scan_id), state, 3600)


def _append_result(scan_id: str, result: dict):
    state = cache.get(_cache_key(scan_id)) or {}
    results = state.get("results") or []
    results.append(result)
    state["results"] = results
    state["devices_found"] = len(results)
    cache.set(_cache_key(scan_id), state, 3600)


def _expand_ip_range(ip_range: str) -> list[str]:
    """Convertit '192.168.1.0/24' ou '192.168.1.1-254' → liste d'IPs."""
    ip_range = ip_range.strip()
    if not ip_range:
        return []
    # CIDR
    if "/" in ip_range:
        try:
            net = ipaddress.ip_network(ip_range, strict=False)
            return [str(ip) for ip in net.hosts()]
        except ValueError as exc:
            raise ValueError(f"CIDR invalide : {exc}")
    # Range dotté (192.168.1.1-254)
    if "-" in ip_range:
        try:
            base, end = ip_range.rsplit("-", 1)
            base_parts = base.split(".")
            start_last = int(base_parts[-1])
            end_last = int(end)
            prefix = ".".join(base_parts[:-1])
            return [f"{prefix}.{i}" for i in range(start_last, end_last + 1)]
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Plage IP invalide : {exc}")
    # IP unique
    try:
        ipaddress.ip_address(ip_range)
        return [ip_range]
    except ValueError:
        raise ValueError(f"Format IP non reconnu : {ip_range}")


def _probe_ip(ip: str, ports: list[int], timeout_s: float = TIMEOUT_S) -> Optional[dict]:
    """Sonde un IP sur plusieurs ports. Retourne dict si au moins 1 port ouvert."""
    open_ports = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout_s)
                if s.connect_ex((ip, port)) == 0:
                    open_ports.append(port)
        except Exception:
            pass

    if not open_ports:
        return None

    # Détection protocole & type
    protocol = None
    detected_type = None
    for p in open_ports:
        hint = PORT_HINTS.get(p)
        if hint:
            protocol = protocol or hint[0]
            detected_type = detected_type or hint[1]

    # MAC via ARP (best-effort, Linux only)
    mac = _get_mac_from_arp(ip)

    # Vérifie si déjà connu dans Shield
    already_known = _is_known(ip)

    return {
        "ip": ip,
        "mac": mac,
        "ports": open_ports,
        "protocol": protocol,
        "detected_type": detected_type,
        "already_known": already_known,
    }


def _get_mac_from_arp(ip: str) -> Optional[str]:
    """Lit la MAC via /proc/net/arp (Linux). Retourne None sinon."""
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    mac = parts[3]
                    if mac != "00:00:00:00:00:00":
                        return mac
    except Exception:
        pass
    return None


def _is_known(ip: str) -> bool:
    """Vérifie si un Device avec cette IP existe déjà."""
    try:
        from .models import Device
        return Device.objects.filter(ip_address=ip).exists()
    except Exception:
        return False


def _run_scan(scan_id: str, ips: list[str], ports: list[int], timeout_ms: int):
    """Thread background : parcourt la plage IP en parallèle."""
    timeout_s = max(timeout_ms / 1000, 0.2)
    _append_log(scan_id, f"Scan démarré : {len(ips)} IP à sonder, ports {ports}")

    scanned = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_probe_ip, ip, ports, timeout_s): ip for ip in ips}
        for fut in as_completed(futures):
            ip = futures[fut]

            # Check cancellation
            state = cache.get(_cache_key(scan_id)) or {}
            if state.get("cancelled"):
                _append_log(scan_id, "Scan annulé par l'utilisateur")
                pool.shutdown(cancel_futures=True, wait=False)
                _update(scan_id, done=True, cancelled=True)
                return

            try:
                result = fut.result()
                if result:
                    _append_result(scan_id, result)
                    hint = f" ({result['detected_type']})" if result.get("detected_type") else ""
                    _append_log(scan_id, f"✓ {ip} — ports {result['ports']}{hint}")
            except Exception as exc:
                _append_log(scan_id, f"⚠ Erreur sur {ip}: {exc}")

            scanned += 1
            _update(scan_id,
                    ips_scanned=scanned,
                    progress=int(scanned * 100 / max(len(ips), 1)))

    _append_log(scan_id, f"Scan terminé — {scanned} IP scannées")
    _update(scan_id, done=True, progress=100, finished_at=datetime.now().isoformat())


def start_scan(ip_range: str, ports: Optional[list[int]] = None,
               timeout_ms: int = 500, user_id: Optional[int] = None) -> str:
    """Lance un scan réseau non bloquant. Retourne le scan_id.

    Lève ValueError si la plage IP est mal formée.
    Rate-limite : max 1 scan actif par user.
    """
    ips = _expand_ip_range(ip_range)
    if not ips:
        raise ValueError("Plage IP vide")
    if len(ips) > 1024:
        raise ValueError(f"Plage trop large ({len(ips)} IPs) — max 1024")

    ports = ports or DEFAULT_PORTS
    scan_id = str(uuid.uuid4())

    # État initial
    cache.set(_cache_key(scan_id), {
        "scan_id": scan_id,
        "ip_range": ip_range,
        "total_ips": len(ips),
        "ips_scanned": 0,
        "progress": 0,
        "devices_found": 0,
        "new_devices": 0,
        "unknown": 0,
        "results": [],
        "logs": [],
        "started_at": datetime.now().isoformat(),
        "started_by": user_id,
        "done": False,
        "cancelled": False,
    }, 3600)

    # Thread background — daemon pour ne pas bloquer le shutdown gunicorn
    thread = threading.Thread(
        target=_run_scan,
        args=(scan_id, ips, ports, timeout_ms),
        daemon=True,
        name=f"netscan-{scan_id[:8]}",
    )
    thread.start()

    logger.info("Network scan started: %s range=%s ips=%d by user=%s",
                scan_id, ip_range, len(ips), user_id)
    return scan_id


def get_scan_status(scan_id: str) -> Optional[dict]:
    return cache.get(_cache_key(scan_id))


def cancel_scan(scan_id: str) -> bool:
    state = cache.get(_cache_key(scan_id))
    if not state:
        return False
    state["cancelled"] = True
    cache.set(_cache_key(scan_id), state, 3600)
    return True


def adopt_device(scan_id: str, ip: str, defaults: Optional[dict] = None,
                 user=None) -> dict:
    """Crée un Device dans Shield à partir d'un résultat de scan.

    Retourne {device_id, created, message} ou lève ValueError.
    """
    from .models import Device, DeviceModel

    state = get_scan_status(scan_id)
    if not state:
        raise ValueError("Scan inconnu ou expiré")

    result = next((r for r in state.get("results", []) if r["ip"] == ip), None)
    if not result:
        raise ValueError(f"IP {ip} non trouvée dans les résultats du scan")

    # Vérifie qu'il n'existe pas déjà
    existing = Device.objects.filter(ip_address=ip).first()
    if existing:
        return {
            "device_id": existing.id,
            "created": False,
            "message": f"Device {existing.serial_number} existe déjà pour cette IP",
        }

    defaults = defaults or {}
    detected_type = result.get("detected_type") or "unknown"

    # Trouve un DeviceModel générique ou crée-en un
    dm, _ = DeviceModel.objects.get_or_create(
        brand="Discovered", model=f"scan-{detected_type}",
        defaults={"type": detected_type if detected_type != "unknown" else "reader_nfc_fixed",
                  "is_active": True},
    )

    # Résout le tenant du user
    tenant = getattr(user, "tenant", None)
    if not tenant:
        try:
            from core.services import get_kaydan_tenant
            tenant = get_kaydan_tenant()
        except Exception:
            pass
    if not tenant:
        raise ValueError("Tenant introuvable pour l'utilisateur")

    device = Device.objects.create(
        tenant=tenant,
        model=dm,
        serial_number=defaults.get("serial_number") or f"AUTO-{ip.replace('.', '-')}",
        ip_address=ip,
        mac_address=result.get("mac") or "",
        status="active",
    )

    logger.info("Device %s adopté depuis scan %s (IP=%s)", device.id, scan_id, ip)
    return {
        "device_id": device.id,
        "created": True,
        "message": f"Device {device.serial_number} créé",
    }
