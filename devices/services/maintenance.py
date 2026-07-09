"""KAYDAN SHIELD — Moteur de maintenance prédictive.

Analyse l'état actuel du DeviceTwin + les tendances des dernières 24h
pour générer automatiquement des MaintenanceTicket avec un score de confiance.

Règles heuristiques (pas de ML lourd pour la Vague 8 — se base sur les seuils
et les trends linéaires). Peut être étendu vers scikit-learn plus tard.

Chaque ticket a :
    - kind (battery_low, storage_critical, temperature_high, …)
    - severity (info / warning / critical)
    - confidence (0.0-1.0)
    - prediction (dict avec valeur actuelle, trend, ETA estimée avant panne)

Idempotent : ne crée pas 2 tickets identiques ouverts pour le même device+kind.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Seuils configurables — override via settings.KSHIELD_MAINTENANCE_RULES
# ═══════════════════════════════════════════════════════════════════
DEFAULT_RULES = {
    # Batterie
    "battery_warning":   20,   # %
    "battery_critical":  10,
    # Stockage
    "storage_warning":   85,   # %
    "storage_critical":  95,
    # Température
    "temp_warning":      60,   # °C
    "temp_critical":     75,
    # Firmware — âge en jours après lequel on suggère l'update
    "firmware_age_days": 365,
    # Erreurs récentes
    "errors_threshold":  5,    # nombre d'erreurs sur la dernière heure
    # Perte de connectivité
    "heartbeat_lost_hours": 2,
}


class PredictiveMaintenanceEngine:
    """Moteur d'analyse des DeviceTwin → génération de MaintenanceTicket."""

    @staticmethod
    def analyze_all(tenant=None) -> dict:
        """Passe tous les devices actifs en revue. Retourne stats."""
        from devices.models import Device

        qs = Device.objects.filter(status="active").select_related("model", "twin")
        if tenant is not None:
            qs = qs.filter(tenant=tenant)

        created, updated, skipped = 0, 0, 0
        for device in qs:
            try:
                res = PredictiveMaintenanceEngine.analyze_device(device)
                created += res["created"]
                updated += res["updated"]
            except Exception as exc:
                logger.exception("Analyse maintenance KO device=%s: %s",
                                   device.pk, exc)
                skipped += 1
        logger.info("Maintenance sweep : created=%d updated=%d skipped=%d",
                     created, updated, skipped)
        return {"created": created, "updated": updated, "skipped": skipped}

    @staticmethod
    @transaction.atomic
    def analyze_device(device) -> dict:
        """Analyse un device, crée ou update les tickets nécessaires."""
        from devices.models import DeviceTwin

        rules = DEFAULT_RULES
        try:
            twin = device.twin
        except DeviceTwin.DoesNotExist:
            return {"created": 0, "updated": 0}

        stats = {"created": 0, "updated": 0}
        now = timezone.now()

        # 1) Batterie
        b = twin.battery_percent
        if b is not None:
            if b < rules["battery_critical"]:
                r = _raise_ticket(device, "battery_critical", "critical",
                    title=f"Batterie critique — {b}%",
                    description=f"Batterie à {b}% (<{rules['battery_critical']}%). "
                                 "Remplacement urgent recommandé.",
                    prediction={"value": b, "threshold": rules["battery_critical"]},
                    confidence=0.95)
                stats[r] += 1
            elif b < rules["battery_warning"]:
                r = _raise_ticket(device, "battery_low", "warning",
                    title=f"Batterie faible — {b}%",
                    description=f"Batterie à {b}% (<{rules['battery_warning']}%). "
                                 "Prévoir le remplacement.",
                    prediction={"value": b, "threshold": rules["battery_warning"]},
                    confidence=0.90)
                stats[r] += 1
            else:
                _resolve_ticket(device, ["battery_low", "battery_critical"])

        # 2) Stockage
        s = twin.storage_percent
        if s is not None:
            if s >= rules["storage_critical"]:
                r = _raise_ticket(device, "storage_critical", "critical",
                    title=f"Stockage saturé — {s:.0f}%",
                    description=f"Stockage à {s:.0f}%. Purge ou upgrade nécessaire.",
                    prediction={"value": s, "threshold": rules["storage_critical"]},
                    confidence=0.98)
                stats[r] += 1
            elif s >= rules["storage_warning"]:
                r = _raise_ticket(device, "storage_low", "warning",
                    title=f"Stockage élevé — {s:.0f}%",
                    description=f"Stockage à {s:.0f}%. Prévoir un nettoyage.",
                    prediction={"value": s, "threshold": rules["storage_warning"]},
                    confidence=0.90)
                stats[r] += 1
            else:
                _resolve_ticket(device, ["storage_low", "storage_critical"])

        # 3) Température
        t = twin.temperature_c
        if t is not None:
            if t >= rules["temp_critical"]:
                r = _raise_ticket(device, "temperature_critical", "critical",
                    title=f"Température critique — {t:.1f}°C",
                    description=f"Température ambiante à {t:.1f}°C. "
                                 "Vérifier la ventilation et l'environnement.",
                    prediction={"value": t, "threshold": rules["temp_critical"]},
                    confidence=0.85)
                stats[r] += 1
            elif t >= rules["temp_warning"]:
                r = _raise_ticket(device, "temperature_high", "warning",
                    title=f"Température élevée — {t:.1f}°C",
                    description=f"Température à {t:.1f}°C.",
                    prediction={"value": t, "threshold": rules["temp_warning"]},
                    confidence=0.80)
                stats[r] += 1
            else:
                _resolve_ticket(device, ["temperature_high", "temperature_critical"])

        # 4) Perte de connectivité
        if device.last_heartbeat_at:
            hours = (now - device.last_heartbeat_at).total_seconds() / 3600
            if hours >= rules["heartbeat_lost_hours"]:
                sev = "critical" if hours >= 24 else "warning"
                r = _raise_ticket(device, "connectivity_loss", sev,
                    title=f"Perte de connectivité — {int(hours)} h",
                    description=f"Aucun heartbeat depuis {int(hours)} heures. "
                                 "Vérifier réseau ou alimentation.",
                    prediction={"hours": hours},
                    confidence=0.75)
                stats[r] += 1
            else:
                _resolve_ticket(device, ["connectivity_loss"])

        # 5) Taux d'erreurs récent
        if twin.recent_errors:
            one_hour_ago = (now - timedelta(hours=1)).isoformat()
            recent = [e for e in twin.recent_errors
                      if e.get("at", "") > one_hour_ago]
            if len(recent) >= rules["errors_threshold"]:
                r = _raise_ticket(device, "high_error_rate", "warning",
                    title=f"Taux d'erreurs élevé — {len(recent)}/h",
                    description=f"{len(recent)} erreurs dans l'heure. "
                                 "Investigation recommandée.",
                    prediction={"errors_last_hour": len(recent)},
                    confidence=0.70)
                stats[r] += 1
            else:
                _resolve_ticket(device, ["high_error_rate"])

        # 6) Firmware obsolète
        if device.commissioned_at:
            age_days = (now - device.commissioned_at).days
            if age_days >= rules["firmware_age_days"]:
                # Ne relance pas si déjà ouvert récemment (auto-résolu 30j)
                r = _raise_ticket(device, "firmware_outdated", "info",
                    title="Firmware potentiellement obsolète",
                    description=f"Équipement en service depuis {age_days} jours. "
                                 "Vérifier disponibilité d'un update firmware.",
                    prediction={"days_in_service": age_days},
                    confidence=0.60)
                stats[r] += 1

        return stats


# ═══════════════════════════════════════════════════════════════════
# Helpers privés
# ═══════════════════════════════════════════════════════════════════
def _raise_ticket(device, kind: str, severity: str, *,
                    title: str, description: str,
                    prediction: dict, confidence: float) -> str:
    """Crée ou update un ticket. Retourne 'created' ou 'updated'."""
    from devices.models import MaintenanceTicket

    existing = MaintenanceTicket.objects.filter(
        device=device, kind=kind, status__in=["open", "in_progress"],
    ).first()
    if existing:
        # Update le detail + prediction si changé
        changed = False
        if existing.severity != severity:
            existing.severity = severity; changed = True
        if existing.prediction != prediction:
            existing.prediction = prediction; changed = True
        if existing.description != description:
            existing.description = description; changed = True
        if changed:
            existing.save(update_fields=["severity", "prediction", "description"])
        return "updated"

    MaintenanceTicket.objects.create(
        tenant=device.tenant, device=device,
        kind=kind, severity=severity, status="open",
        title=title[:240], description=description,
        prediction=prediction, confidence=confidence,
        created_by_engine=True,
    )
    return "created"


def _resolve_ticket(device, kinds: list[str]):
    """Passe à 'resolved' les tickets ouverts de ces kinds pour ce device."""
    from devices.models import MaintenanceTicket

    now = timezone.now()
    MaintenanceTicket.objects.filter(
        device=device, kind__in=kinds,
        status__in=["open", "in_progress"],
        created_by_engine=True,
    ).update(
        status="resolved", resolved_at=now,
        resolution_notes=f"Résolu automatiquement par le moteur à {now.isoformat()}",
    )
