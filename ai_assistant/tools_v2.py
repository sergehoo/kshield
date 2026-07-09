"""KAYDAN SHIELD — Shield IA v2 tools (Vague 8).

Étend le système de function-calling existant avec :
    - device_ping           — ping via driver vendor
    - device_twin_get       — état runtime + health score
    - device_twin_refresh   — force un refresh via driver
    - driver_list           — liste des drivers chargés
    - discovery_scan        — scan multi-protocole
    - enrollment_start      — démarre une session d'enrôlement RFID
    - enrollment_stop       — arrête une session
    - maintenance_list      — tickets ouverts
    - maintenance_create    — création manuelle d'un ticket

Tous les tools sont enregistrés via ``@register_tool`` du module tools.py existant.
"""
from __future__ import annotations

import logging
from typing import Optional

from .tools import register_tool

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Device — ping + twin
# ═══════════════════════════════════════════════════════════════════
@register_tool(schema={
    "name": "device_ping",
    "description": (
        "Teste la connectivité d'un équipement via son driver vendor. "
        "Retourne latence et informations d'identification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {"type": "integer", "description": "ID du Device"},
        },
        "required": ["device_id"],
    },
}, permission="devices.view")
def device_ping(device_id: int, user=None):
    from devices.drivers import DriverManager
    from devices.models import Device
    try:
        device = Device.objects.select_related("model").get(pk=device_id)
    except Device.DoesNotExist:
        return {"error": f"Device {device_id} introuvable"}
    driver = DriverManager.for_device(device)
    try:
        with driver:
            r = driver.ping()
            return {
                "driver": driver.__class__.__name__,
                "vendor": driver.vendor,
                "reachable": r.ok,
                "detail": r.detail,
                "data": r.data,
            }
    except Exception as exc:
        return {"error": str(exc)}


@register_tool(schema={
    "name": "device_twin_get",
    "description": (
        "Retourne le Digital Twin d'un équipement : état runtime "
        "(CPU/RAM/stockage/temp/batterie), health score et raisons."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {"type": "integer", "description": "ID du Device"},
        },
        "required": ["device_id"],
    },
}, permission="devices.view")
def device_twin_get(device_id: int, user=None):
    from devices.models import Device
    from devices.services import TwinService
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {"error": "Device introuvable"}
    twin = TwinService.get_or_create(device)
    return {
        "device_id": device.pk,
        "serial": device.serial_number,
        "reachable": twin.reachable,
        "health_score": twin.health_score,
        "health_status": twin.health_status,
        "health_reasons": twin.health_reasons,
        "metrics": {
            "cpu_percent": twin.cpu_percent,
            "ram_percent": twin.ram_percent,
            "storage_percent": twin.storage_percent,
            "temperature_c": twin.temperature_c,
            "battery_percent": twin.battery_percent,
            "latency_ms": twin.latency_ms,
            "uptime_seconds": twin.uptime_seconds,
        },
        "last_seen_at": twin.last_seen_at.isoformat() if twin.last_seen_at else None,
    }


@register_tool(schema={
    "name": "device_twin_refresh",
    "description": (
        "Force un refresh immédiat du Digital Twin en appelant le driver vendor. "
        "Utile pour vérifier l'état actuel avant une action."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {"type": "integer"},
        },
        "required": ["device_id"],
    },
}, permission="devices.manage", is_action=True)
def device_twin_refresh(device_id: int, user=None):
    from devices.models import Device
    from devices.services import TwinService
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {"error": "Device introuvable"}
    twin = TwinService.refresh(device, use_driver=True)
    return {
        "device_id": device.pk,
        "reachable": twin.reachable,
        "health_score": twin.health_score,
        "refreshed_at": twin.last_probed_at.isoformat() if twin.last_probed_at else None,
    }


# ═══════════════════════════════════════════════════════════════════
# Drivers + Discovery
# ═══════════════════════════════════════════════════════════════════
@register_tool(schema={
    "name": "driver_list",
    "description": "Liste tous les drivers vendor chargés (Hikvision, ZKTeco, Suprema…) avec leurs capabilities.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}, permission="devices.view")
def driver_list(user=None):
    from devices.drivers import DriverManager
    return {"drivers": DriverManager.list_drivers()}


@register_tool(schema={
    "name": "discovery_scan",
    "description": (
        "Lance un scan Auto Discovery multi-protocole sur le LAN. "
        "Détecte les équipements ONVIF, mDNS, SSDP, SNMP et ARP."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "protocols": {
                "type": "array", "items": {"type": "string"},
                "description": "Liste des protocoles à utiliser (défaut : tous sauf snmp).",
            },
            "ip_range": {
                "type": "string",
                "description": "Plage IP pour SNMP+TCP (ex. 192.168.1.0/24)",
            },
            "timeout": {"type": "number", "description": "Timeout par protocole (défaut 4s)"},
        },
    },
}, permission="devices.manage", is_action=True)
def discovery_scan(protocols: Optional[list] = None,
                    ip_range: Optional[str] = None,
                    timeout: float = 4.0, user=None):
    from devices.discovery import DiscoveryOrchestrator
    from devices.network_scan import _expand_ip_range

    ips = None
    if ip_range:
        try:
            ips = _expand_ip_range(ip_range)
        except ValueError as exc:
            return {"error": str(exc)}
    orch = DiscoveryOrchestrator(protocols=protocols or ["onvif", "mdns", "ssdp", "arp"],
                                    timeout=timeout)
    devices = orch.scan(ips)
    return {
        "count": len(devices),
        "devices": [
            {"ip": d.ip, "mac": d.mac, "vendor": d.vendor,
              "device_type_hint": d.device_type_hint,
              "protocols_detected": d.protocols_detected,
              "already_known": d.already_known}
            for d in devices
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# Enrôlement
# ═══════════════════════════════════════════════════════════════════
@register_tool(schema={
    "name": "enrollment_start",
    "description": (
        "Démarre une session d'enrôlement RFID sur un lecteur donné, "
        "en pré-associant éventuellement un ouvrier ou employé."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reader_id": {"type": "integer", "description": "ID du Device lecteur"},
            "mode": {"type": "string", "enum": ["single", "bulk"], "description": "Mode d'enrôlement"},
            "holder_kind": {"type": "string", "enum": ["worker", "employee", "visitor", ""]},
            "holder_id": {"type": "integer"},
            "timeout_seconds": {"type": "integer"},
        },
        "required": ["reader_id"],
    },
}, permission="badges.manage", is_action=True)
def enrollment_start(reader_id: int, mode: str = "single",
                      holder_kind: str = "", holder_id: Optional[int] = None,
                      timeout_seconds: int = 180, user=None):
    from devices.models import Device
    from devices.services.enrollment import (EnrollmentError,
                                                RFIDEnrollmentService)
    try:
        reader = Device.objects.get(pk=reader_id)
    except Device.DoesNotExist:
        return {"error": "Reader introuvable"}
    try:
        session = RFIDEnrollmentService.start_session(
            user=user, reader=reader, mode=mode,
            holder_kind=holder_kind or "", holder_id=holder_id,
            timeout_seconds=timeout_seconds,
        )
    except EnrollmentError as exc:
        return {"error": exc.message, "code": exc.code}
    return {"session_id": str(session.pk), "status": session.status,
             "channel_group": session.channel_group}


@register_tool(schema={
    "name": "enrollment_stop",
    "description": "Arrête une session d'enrôlement RFID.",
    "parameters": {
        "type": "object",
        "properties": {"session_id": {"type": "string"}},
        "required": ["session_id"],
    },
}, permission="badges.manage", is_action=True)
def enrollment_stop(session_id: str, user=None):
    from devices.models import RFIDEnrollmentSession
    from devices.services.enrollment import RFIDEnrollmentService
    try:
        s = RFIDEnrollmentSession.objects.get(pk=session_id)
    except RFIDEnrollmentSession.DoesNotExist:
        return {"error": "Session introuvable"}
    s = RFIDEnrollmentService.stop_session(s, user=user, reason="ai_stop")
    return {"session_id": str(s.pk), "status": s.status,
             "scans_count": s.scans_count}


# ═══════════════════════════════════════════════════════════════════
# Maintenance
# ═══════════════════════════════════════════════════════════════════
@register_tool(schema={
    "name": "maintenance_list",
    "description": "Liste les tickets de maintenance ouverts, filtrables par sévérité.",
    "parameters": {
        "type": "object",
        "properties": {
            "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            "limit": {"type": "integer"},
        },
    },
}, permission="devices.view")
def maintenance_list(severity: Optional[str] = None, limit: int = 20, user=None):
    from devices.models import MaintenanceTicket
    tenant = getattr(user, "tenant", None) if user else None
    qs = MaintenanceTicket.objects.filter(status__in=["open", "in_progress"])
    if tenant:
        qs = qs.filter(tenant=tenant)
    if severity:
        qs = qs.filter(severity=severity)
    qs = qs.select_related("device").order_by("-created_at")[:limit]
    return {
        "tickets": [
            {
                "id": str(t.pk), "device_id": t.device_id,
                "device_serial": t.device.serial_number if t.device_id else None,
                "kind": t.kind, "severity": t.severity, "status": t.status,
                "title": t.title, "confidence": t.confidence,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in qs
        ],
    }


@register_tool(schema={
    "name": "maintenance_create",
    "description": "Crée manuellement un ticket de maintenance.",
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {"type": "integer"},
            "kind": {"type": "string"},
            "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            "title": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["device_id", "title"],
    },
}, permission="devices.manage", is_action=True)
def maintenance_create(device_id: int, title: str,
                        kind: str = "manual", severity: str = "warning",
                        description: str = "", user=None):
    from devices.models import Device, MaintenanceTicket
    tenant = getattr(user, "tenant", None) if user else None
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {"error": "Device introuvable"}
    t = MaintenanceTicket.objects.create(
        tenant=tenant or device.tenant, device=device,
        kind=kind, severity=severity, status="open",
        title=title[:240], description=description,
        created_by_engine=False,
    )
    return {"ticket_id": str(t.pk), "status": t.status}
