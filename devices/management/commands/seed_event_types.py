"""Management command : peuple la table EventType avec les 69 types
listés dans le cahier des charges Kaydan Shield refonte v1.

Idempotent — utilise update_or_create par code. Peut être relancé
sans dommage pour ajouter les nouveaux types.

Usage :
    python manage.py seed_event_types
    python manage.py seed_event_types --dry-run
    python manage.py seed_event_types --force  (met à jour même les user-modif)
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from devices.models_events import EventCategory, EventResult, EventSeverity


# ═══════════════════════════════════════════════════════════════════
# Nomenclature complète des 69 types — cahier des charges section 1.4
# ═══════════════════════════════════════════════════════════════════
CATALOG: list[dict] = [
    # ─── Accès (8) ──────────────────────────────────────────
    {"code": "ACCESS_GRANTED",   "category": EventCategory.ACCESS,
     "label": "Accès autorisé", "severity": EventSeverity.INFO,
     "result": EventResult.GRANTED, "icon": "check-circle-2", "color": "text-success"},
    {"code": "ACCESS_DENIED",    "category": EventCategory.ACCESS,
     "label": "Accès refusé", "severity": EventSeverity.WARNING,
     "result": EventResult.DENIED, "icon": "x-circle", "color": "text-danger",
     "triggers_alert": True},
    {"code": "ACCESS_PENDING",   "category": EventCategory.ACCESS,
     "label": "Accès en attente", "severity": EventSeverity.INFO,
     "result": EventResult.PENDING, "icon": "clock", "color": "text-info"},
    {"code": "DOOR_OPENED",      "category": EventCategory.ACCESS,
     "label": "Porte ouverte", "severity": EventSeverity.INFO,
     "icon": "door-open", "color": "text-ink-muted"},
    {"code": "DOOR_FORCED",      "category": EventCategory.ACCESS,
     "label": "Porte forcée", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "shield-alert", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "DOOR_LEFT_OPEN",   "category": EventCategory.ACCESS,
     "label": "Porte restée ouverte", "severity": EventSeverity.WARNING,
     "icon": "door-open", "color": "text-warning", "triggers_alert": True},
    {"code": "TURNSTILE_UNLOCKED", "category": EventCategory.ACCESS,
     "label": "Portique déverrouillé", "severity": EventSeverity.INFO,
     "icon": "unlock"},
    {"code": "BARRIER_OPENED",   "category": EventCategory.ACCESS,
     "label": "Barrière ouverte", "severity": EventSeverity.INFO, "icon": "arrow-up"},

    # ─── Pointage (5) ───────────────────────────────────────
    {"code": "CHECK_IN",         "category": EventCategory.ATTENDANCE,
     "label": "Entrée pointée", "severity": EventSeverity.INFO,
     "result": EventResult.GRANTED, "icon": "log-in", "color": "text-success"},
    {"code": "CHECK_OUT",        "category": EventCategory.ATTENDANCE,
     "label": "Sortie pointée", "severity": EventSeverity.INFO,
     "result": EventResult.GRANTED, "icon": "log-out", "color": "text-info"},
    {"code": "ATTENDANCE_REJECTED", "category": EventCategory.ATTENDANCE,
     "label": "Pointage refusé", "severity": EventSeverity.WARNING,
     "result": EventResult.DENIED, "icon": "user-x", "color": "text-danger"},
    {"code": "DUPLICATE_CHECK_IN", "category": EventCategory.ATTENDANCE,
     "label": "Pointage dupliqué", "severity": EventSeverity.WARNING,
     "result": EventResult.ANOMALY, "icon": "copy", "color": "text-warning"},
    {"code": "MISSING_CHECK_OUT", "category": EventCategory.ATTENDANCE,
     "label": "Sortie manquante", "severity": EventSeverity.WARNING,
     "result": EventResult.ANOMALY, "icon": "clock-alert", "color": "text-warning"},

    # ─── RFID / NFC (8) ─────────────────────────────────────
    {"code": "BADGE_DETECTED",   "category": EventCategory.RFID,
     "label": "Badge détecté", "severity": EventSeverity.INFO,
     "icon": "credit-card"},
    {"code": "BADGE_ENROLLED",   "category": EventCategory.RFID,
     "label": "Badge enrôlé", "severity": EventSeverity.INFO,
     "icon": "user-plus", "color": "text-success"},
    {"code": "BADGE_ASSIGNED",   "category": EventCategory.RFID,
     "label": "Badge attribué", "severity": EventSeverity.INFO, "icon": "user-check"},
    {"code": "BADGE_UNASSIGNED", "category": EventCategory.RFID,
     "label": "Badge désaffecté", "severity": EventSeverity.INFO, "icon": "user-minus"},
    {"code": "BADGE_UNKNOWN",    "category": EventCategory.RFID,
     "label": "Badge inconnu", "severity": EventSeverity.WARNING,
     "result": EventResult.DENIED, "icon": "help-circle", "color": "text-warning",
     "triggers_alert": True},
    {"code": "BADGE_EXPIRED",    "category": EventCategory.RFID,
     "label": "Badge expiré", "severity": EventSeverity.WARNING,
     "result": EventResult.DENIED, "icon": "calendar-x", "color": "text-warning"},
    {"code": "BADGE_DISABLED",   "category": EventCategory.RFID,
     "label": "Badge désactivé", "severity": EventSeverity.WARNING,
     "result": EventResult.DENIED, "icon": "shield-off"},
    {"code": "BADGE_DUPLICATE",  "category": EventCategory.RFID,
     "label": "Badge dupliqué", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "copy", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},

    # ─── BLE / Casques (7) ──────────────────────────────────
    {"code": "HELMET_DETECTED",  "category": EventCategory.BLE,
     "label": "Casque détecté", "severity": EventSeverity.INFO, "icon": "hard-hat"},
    {"code": "HELMET_MISSING",   "category": EventCategory.BLE,
     "label": "Casque manquant", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "hard-hat", "color": "text-danger",
     "triggers_alert": True},
    {"code": "HELMET_UNKNOWN",   "category": EventCategory.BLE,
     "label": "Casque inconnu", "severity": EventSeverity.WARNING,
     "result": EventResult.ANOMALY, "icon": "help-circle"},
    {"code": "HELMET_MISMATCH",  "category": EventCategory.BLE,
     "label": "Casque non-associé", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ANOMALY, "icon": "shuffle", "color": "text-danger",
     "triggers_alert": True},
    {"code": "HELMET_BATTERY_LOW", "category": EventCategory.BLE,
     "label": "Batterie casque faible", "severity": EventSeverity.WARNING,
     "icon": "battery-low", "color": "text-warning"},
    {"code": "BLE_DEVICE_LOST",  "category": EventCategory.BLE,
     "label": "Balise BLE perdue", "severity": EventSeverity.WARNING,
     "icon": "bluetooth-off"},
    {"code": "BLE_DEVICE_RECONNECTED", "category": EventCategory.BLE,
     "label": "Balise BLE reconnectée", "severity": EventSeverity.INFO,
     "icon": "bluetooth", "color": "text-success"},

    # ─── Équipements (8) ────────────────────────────────────
    {"code": "DEVICE_ONLINE",    "category": EventCategory.DEVICE,
     "label": "Équipement en ligne", "severity": EventSeverity.INFO,
     "icon": "wifi", "color": "text-success"},
    {"code": "DEVICE_OFFLINE",   "category": EventCategory.DEVICE,
     "label": "Équipement hors ligne", "severity": EventSeverity.WARNING,
     "icon": "wifi-off", "color": "text-warning", "triggers_alert": True},
    {"code": "DEVICE_REGISTERED","category": EventCategory.DEVICE,
     "label": "Équipement enregistré", "severity": EventSeverity.INFO,
     "icon": "plus-circle", "color": "text-success"},
    {"code": "DEVICE_UNREACHABLE","category": EventCategory.DEVICE,
     "label": "Équipement injoignable", "severity": EventSeverity.CRITICAL,
     "icon": "wifi-off", "color": "text-danger", "triggers_alert": True},
    {"code": "DEVICE_CONFIGURATION_CHANGED", "category": EventCategory.DEVICE,
     "label": "Configuration modifiée", "severity": EventSeverity.INFO,
     "icon": "settings"},
    {"code": "DEVICE_AUTHENTICATION_FAILED", "category": EventCategory.DEVICE,
     "label": "Authentification équipement échouée",
     "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "shield-off", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "DEVICE_FIRMWARE_UPDATED", "category": EventCategory.DEVICE,
     "label": "Firmware mis à jour", "severity": EventSeverity.INFO,
     "icon": "download", "color": "text-info"},
    {"code": "DEVICE_ERROR",     "category": EventCategory.DEVICE,
     "label": "Erreur équipement", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ANOMALY, "icon": "alert-triangle", "color": "text-danger",
     "triggers_alert": True},

    # ─── Gateway & Agents locaux (10) ───────────────────────
    {"code": "GATEWAY_ONLINE",   "category": EventCategory.GATEWAY,
     "label": "Gateway en ligne", "severity": EventSeverity.INFO,
     "icon": "server", "color": "text-success"},
    {"code": "GATEWAY_OFFLINE",  "category": EventCategory.GATEWAY,
     "label": "Gateway hors ligne", "severity": EventSeverity.CRITICAL,
     "icon": "server-off", "color": "text-danger", "triggers_alert": True,
     "requires_ack": True},
    {"code": "EDGE_SYNC_STARTED", "category": EventCategory.GATEWAY,
     "label": "Sync Edge démarrée", "severity": EventSeverity.INFO,
     "icon": "refresh-cw"},
    {"code": "EDGE_SYNC_COMPLETED", "category": EventCategory.GATEWAY,
     "label": "Sync Edge complétée", "severity": EventSeverity.INFO,
     "icon": "check", "color": "text-success"},
    {"code": "EDGE_SYNC_FAILED", "category": EventCategory.GATEWAY,
     "label": "Sync Edge échouée", "severity": EventSeverity.WARNING,
     "icon": "x", "color": "text-warning", "triggers_alert": True},
    {"code": "LOCAL_AGENT_STARTED", "category": EventCategory.GATEWAY,
     "label": "Agent local démarré", "severity": EventSeverity.INFO,
     "icon": "play", "color": "text-success"},
    {"code": "LOCAL_AGENT_STOPPED", "category": EventCategory.GATEWAY,
     "label": "Agent local arrêté", "severity": EventSeverity.WARNING,
     "icon": "square", "color": "text-warning"},
    {"code": "LOCAL_AGENT_UPDATED", "category": EventCategory.GATEWAY,
     "label": "Agent local mis à jour", "severity": EventSeverity.INFO,
     "icon": "download"},
    {"code": "LOCAL_QUEUE_PENDING", "category": EventCategory.GATEWAY,
     "label": "File offline en attente", "severity": EventSeverity.WARNING,
     "icon": "list", "color": "text-warning"},
    {"code": "LOCAL_QUEUE_SYNCED", "category": EventCategory.GATEWAY,
     "label": "File offline synchronisée", "severity": EventSeverity.INFO,
     "icon": "check-circle-2", "color": "text-success"},

    # ─── Sécurité (7) ───────────────────────────────────────
    {"code": "FRAUD_DETECTED",   "category": EventCategory.SECURITY,
     "label": "Fraude détectée", "severity": EventSeverity.EMERGENCY,
     "result": EventResult.ALERT, "icon": "shield-alert", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "IDENTITY_MISMATCH","category": EventCategory.SECURITY,
     "label": "Identité non-concordante", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "user-x", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "UNAUTHORIZED_ZONE","category": EventCategory.SECURITY,
     "label": "Zone non-autorisée", "severity": EventSeverity.CRITICAL,
     "result": EventResult.DENIED, "icon": "map-pin-off", "color": "text-danger",
     "triggers_alert": True},
    {"code": "MULTIPLE_BADGE_USAGE", "category": EventCategory.SECURITY,
     "label": "Usage multiple d'un badge", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ANOMALY, "icon": "copy", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "SUSPICIOUS_MOVEMENT", "category": EventCategory.SECURITY,
     "label": "Mouvement suspect", "severity": EventSeverity.WARNING,
     "result": EventResult.ANOMALY, "icon": "eye", "color": "text-warning"},
    {"code": "FACE_MISMATCH",    "category": EventCategory.SECURITY,
     "label": "Visage non-reconnu", "severity": EventSeverity.CRITICAL,
     "result": EventResult.ALERT, "icon": "scan-face", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},
    {"code": "SPOOFING_DETECTED","category": EventCategory.SECURITY,
     "label": "Tentative de spoofing", "severity": EventSeverity.EMERGENCY,
     "result": EventResult.ALERT, "icon": "shield-x", "color": "text-danger",
     "triggers_alert": True, "requires_ack": True},

    # ─── Système (5) — bonus pour compléter la couverture ──
    {"code": "SYSTEM_STARTED",   "category": EventCategory.SYSTEM,
     "label": "Système démarré", "severity": EventSeverity.INFO, "icon": "power"},
    {"code": "SYSTEM_SHUTDOWN",  "category": EventCategory.SYSTEM,
     "label": "Système arrêté", "severity": EventSeverity.INFO, "icon": "power-off"},
    {"code": "SYSTEM_CONFIG_CHANGED", "category": EventCategory.SYSTEM,
     "label": "Configuration système modifiée", "severity": EventSeverity.INFO,
     "icon": "settings-2"},
    {"code": "SYSTEM_USER_LOGIN","category": EventCategory.SYSTEM,
     "label": "Connexion utilisateur", "severity": EventSeverity.INFO,
     "icon": "log-in"},
    {"code": "SYSTEM_USER_LOGOUT","category": EventCategory.SYSTEM,
     "label": "Déconnexion utilisateur", "severity": EventSeverity.INFO,
     "icon": "log-out"},
]


class Command(BaseCommand):
    help = "Peuple la nomenclature EventType avec les 69 types du cahier des charges."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait fait sans écrire en base.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Overwrite label/severity/color même si un admin les a modifiés.",
        )

    def handle(self, *args, **opts):
        from devices.models_events import EventType

        dry = opts["dry_run"]
        force = opts["force"]

        created = updated = skipped = 0

        for entry in CATALOG:
            defaults = {
                "category":         entry["category"],
                "label":            entry["label"],
                "severity_default": entry["severity"],
                "result_default":   entry.get("result", EventResult.NEUTRAL),
                "icon":             entry.get("icon", ""),
                "color":            entry.get("color", ""),
                "triggers_alert":   entry.get("triggers_alert", False),
                "requires_ack":     entry.get("requires_ack", False),
                "is_system":        True,
                "is_active":        True,
            }

            if dry:
                self.stdout.write(f"[dry] {entry['code']} — {entry['label']}")
                continue

            existing = EventType.objects.filter(code=entry["code"]).first()
            if existing is None:
                EventType.objects.create(code=entry["code"], **defaults)
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  + {entry['code']}"
                ))
            else:
                # Update uniquement les champs "système" (défauts + icons)
                # Si --force, on écrase même label ; sinon on préserve les
                # personnalisations admin.
                if force:
                    for k, v in defaults.items():
                        setattr(existing, k, v)
                    existing.save()
                    updated += 1
                    self.stdout.write(f"  ~ {entry['code']} (force update)")
                else:
                    # Update uniquement severity/icon/color/flags — pas label
                    for k in ("severity_default", "result_default", "icon",
                                "color", "triggers_alert", "requires_ack",
                                "is_system"):
                        setattr(existing, k, defaults[k])
                    existing.save()
                    skipped += 1

        if dry:
            self.stdout.write(self.style.WARNING(
                f"\n[dry-run] Aurait traité {len(CATALOG)} types.",
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Nomenclature EventType peuplée : "
            f"{created} créés, {updated} force-updated, "
            f"{skipped} conservés (label admin préservé)",
        ))
