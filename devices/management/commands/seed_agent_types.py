"""Management command : peuple la table LocalAgentType avec les 10 codes
définis par le cahier des charges Kaydan Shield refonte §5.

Idempotent — utilise update_or_create par code. Peut être relancé
sans dommage pour ajouter les nouveaux types.

Usage :
    python manage.py seed_agent_types
    python manage.py seed_agent_types --dry-run
    python manage.py seed_agent_types --force
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from devices.models_agents import LocalAgentType


CATALOG: list[dict] = [
    {
        "code": "rfid",
        "label": "Agent RFID",
        "description": "Lecture des badges RFID/NFC via LLRP, PC/SC ou UART.",
        "module_name": "kshield_agent.modules.rfid",
        "icon": "credit-card",
        "capabilities": ["read_uid", "batch_enroll", "sllurp", "pcsc", "uart"],
        "config_schema": {
            "reader_backend": {"type": "enum", "values": ["sllurp", "pcsc", "uart"], "default": "sllurp"},
            "poll_interval_ms": {"type": "int", "min": 100, "max": 5000, "default": 500},
            "auto_enroll": {"type": "bool", "default": False},
        },
        "is_system": True,
    },
    {
        "code": "ble",
        "label": "Agent BLE",
        "description": "Écoute des balises et casques connectés en Bluetooth Low Energy.",
        "module_name": "kshield_agent.modules.ble",
        "icon": "bluetooth",
        "capabilities": ["scan", "advertise", "pair", "gatt_notify"],
        "config_schema": {
            "scan_interval_s": {"type": "int", "min": 1, "max": 60, "default": 5},
            "rssi_threshold": {"type": "int", "min": -100, "max": -30, "default": -80},
        },
        "is_system": True,
    },
    {
        "code": "camera",
        "label": "Agent Caméra",
        "description": "Ingestion événements caméras via ONVIF, ISAPI, RTSP.",
        "module_name": "kshield_agent.modules.camera",
        "icon": "camera",
        "capabilities": ["onvif_events", "isapi_stream", "snapshot", "motion_detect"],
        "config_schema": {
            "protocols": {"type": "list", "default": ["onvif", "isapi"]},
            "snapshot_on_event": {"type": "bool", "default": True},
        },
        "is_system": True,
    },
    {
        "code": "biometric",
        "label": "Agent Biométrique",
        "description": "Enrôlement et matching biométriques (empreinte, visage).",
        "module_name": "kshield_agent.modules.biometric",
        "icon": "fingerprint",
        "capabilities": ["fingerprint", "face", "enroll", "match"],
        "config_schema": {
            "backend": {"type": "enum", "values": ["suprema", "zkteco", "hid"], "default": "suprema"},
            "match_threshold": {"type": "float", "min": 0.5, "max": 0.99, "default": 0.85},
        },
        "is_system": True,
    },
    {
        "code": "attendance",
        "label": "Agent Pointage",
        "description": "Push/Pull des logs de pointage depuis pointeuses ZKTeco/Anviz.",
        "module_name": "kshield_agent.modules.attendance",
        "icon": "clock",
        "capabilities": ["push_http", "pull_sdk", "sync_shifts"],
        "config_schema": {
            "mode": {"type": "enum", "values": ["push", "pull"], "default": "push"},
            "pull_interval_s": {"type": "int", "min": 30, "max": 3600, "default": 300},
        },
        "is_system": True,
    },
    {
        "code": "mqtt",
        "label": "Agent MQTT",
        "description": "Bridge MQTT ↔ cloud, écoute topics devices/agents.",
        "module_name": "kshield_agent.modules.mqtt",
        "icon": "radio",
        "capabilities": ["publish", "subscribe", "bridge", "tls"],
        "config_schema": {
            "broker": {"type": "string", "default": "tls://mqtt.kaydanshield.com:8883"},
            "topics": {"type": "list", "default": ["shield/+/events", "shield/+/heartbeats"]},
        },
        "is_system": True,
    },
    {
        "code": "sync",
        "label": "Agent Sync",
        "description": "Synchronisation offline-first (queue SQLite + batches).",
        "module_name": "kshield_agent.modules.sync",
        "icon": "refresh-cw",
        "capabilities": ["queue_sqlite", "batch_upload", "conflict_detection", "checksums"],
        "config_schema": {
            "batch_size": {"type": "int", "min": 10, "max": 1000, "default": 100},
            "sync_interval_s": {"type": "int", "min": 10, "max": 600, "default": 30},
        },
        "is_system": True,
    },
    {
        "code": "discovery",
        "label": "Agent Discovery",
        "description": "Scan réseau ARP/ONVIF/mDNS/SSDP/SNMP + auto-vendor.",
        "module_name": "kshield_agent.modules.discovery",
        "icon": "search",
        "capabilities": ["arp", "onvif_ws_discovery", "mdns", "ssdp", "snmp", "vendor_oui"],
        "config_schema": {
            "protocols": {"type": "list", "default": ["arp", "onvif", "mdns"]},
            "scan_subnets": {"type": "list", "default": ["192.168.0.0/24"]},
        },
        "is_system": True,
    },
    {
        "code": "monitoring",
        "label": "Agent Monitoring",
        "description": "Surveillance santé locale (CPU, RAM, disque, latence).",
        "module_name": "kshield_agent.modules.monitoring",
        "icon": "activity",
        "capabilities": ["cpu", "memory", "storage", "network_latency", "prometheus_export"],
        "config_schema": {
            "sample_interval_s": {"type": "int", "min": 5, "max": 300, "default": 30},
            "expose_prometheus": {"type": "bool", "default": True},
        },
        "is_system": True,
    },
    {
        "code": "generic",
        "label": "Agent générique",
        "description": "Type par défaut pour agents customisés.",
        "module_name": "kshield_agent.modules.generic",
        "icon": "box",
        "capabilities": [],
        "config_schema": {},
        "is_system": True,
    },
]


class Command(BaseCommand):
    help = "Peuple LocalAgentType avec les 10 codes du cahier des charges §5."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--force", action="store_true",
                            help="Écrase les labels admin-personnalisés.")

    def handle(self, *args, dry_run: bool = False, force: bool = False, **kwargs):
        created = 0
        updated = 0
        skipped = 0
        for entry in CATALOG:
            defaults = {
                "label": entry["label"],
                "description": entry["description"],
                "module_name": entry["module_name"],
                "icon": entry["icon"],
                "capabilities": entry["capabilities"],
                "config_schema": entry["config_schema"],
                "is_active": True,
                "is_system": entry["is_system"],
            }
            if dry_run:
                self.stdout.write(f"[dry] {entry['code']:12} → {entry['label']}")
                continue

            existing = LocalAgentType.objects.filter(code=entry["code"]).first()
            if existing is None:
                LocalAgentType.objects.create(code=entry["code"], **defaults)
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  + {entry['code']}"))
            else:
                if force:
                    for k, v in defaults.items():
                        setattr(existing, k, v)
                    existing.save()
                    updated += 1
                    self.stdout.write(f"  ~ {entry['code']} (force)")
                else:
                    # Conserve label + description admin, met à jour reste
                    for k in ("module_name", "icon", "capabilities",
                              "config_schema", "is_system"):
                        setattr(existing, k, defaults[k])
                    existing.save()
                    skipped += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n[dry] Aurait traité {len(CATALOG)} types."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ LocalAgentType peuplé : "
            f"{created} créés, {updated} force-updated, "
            f"{skipped} conservés"
        ))
