"""KAYDAN SHIELD — Digital Twin service + Health Score.

Le TwinService orchestre le refresh du DeviceTwin en appelant les drivers
et calcule automatiquement un Health Score 0-100.

Utilisation :
    twin = TwinService.refresh(device)        # sync, appelle le driver
    TwinService.refresh_all_async()            # via Celery
    score, reasons = TwinService.compute_health_score(twin)
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Barème du Health Score (0-100)
# ═══════════════════════════════════════════════════════════════════
# Chaque check qui échoue pénalise le score. Plus d'un check peut échouer :
# les malus sont additifs, cappés à 100.
HEALTH_RULES = {
    "unreachable":            60,  # coupe presque tout
    "heartbeat_stale_5min":   20,
    "heartbeat_stale_1h":     40,
    "battery_below_20":       15,
    "battery_below_10":       30,
    "temp_above_60":          10,
    "temp_above_75":          25,
    "cpu_above_80":           10,
    "cpu_above_95":           20,
    "ram_above_85":           10,
    "storage_above_85":       10,
    "storage_above_95":       25,
    "firmware_outdated":       5,
    "recent_errors":          10,
    "latency_high":            5,
}


class TwinService:
    """Façade pour lire/écrire le Digital Twin d'un équipement."""

    # ────────────────────────────────────────────────────────────
    # Ensure twin exists
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def get_or_create(device):
        from devices.models import DeviceTwin
        twin, _ = DeviceTwin.objects.get_or_create(device=device)
        return twin

    # ────────────────────────────────────────────────────────────
    # Refresh via driver
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def refresh(device, *, use_driver: bool = True):
        """Rafraîchit le twin d'un device — appelle driver.get_status() si activé."""
        from devices.drivers import DriverManager

        twin = TwinService.get_or_create(device)
        now = timezone.now()
        twin.last_probed_at = now

        status = None
        if use_driver:
            driver = DriverManager.for_device(device)
            twin.driver_class = driver.__class__.__name__
            try:
                with driver:
                    status = driver.get_status()
            except Exception as exc:
                logger.warning("Driver %s get_status KO : %s",
                                driver.__class__.__name__, exc)
                _append_error(twin, str(exc))

        if status is not None:
            twin.reachable = status.reachable
            twin.latency_ms = status.latency_ms
            twin.uptime_seconds = status.uptime_seconds
            twin.cpu_percent = status.cpu_percent
            twin.ram_percent = status.ram_percent
            twin.storage_percent = status.storage_percent
            twin.temperature_c = status.temperature_c
            twin.battery_percent = status.battery_percent
            twin.network_quality = status.network_quality
            twin.firmware = status.firmware or twin.firmware
            twin.raw_status = status.raw or {}
            if status.errors:
                for e in status.errors[:5]:
                    _append_error(twin, e)
            if status.reachable:
                twin.last_seen_at = now
        else:
            # Fallback : reachable = heartbeat récent
            twin.reachable = bool(
                device.last_heartbeat_at
                and device.last_heartbeat_at > now - timedelta(seconds=90)
            )
            if twin.reachable:
                twin.last_seen_at = device.last_heartbeat_at

        # Calcul health score
        score, reasons = TwinService.compute_health_score(twin, device)
        twin.health_score = score
        twin.health_reasons = reasons
        twin.save()

        # Métrique Prometheus (moyenne globale des scores)
        try:
            from core.metrics import devices_online
            # On log par site pour ventiler
            devices_online.labels(device_type=device.model.type or "unknown").set(
                1 if twin.reachable else 0,
            )
        except Exception:
            pass

        return twin

    # ────────────────────────────────────────────────────────────
    # Health Score calculator
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def compute_health_score(twin, device=None) -> tuple[int, list[str]]:
        """Retourne (score, reasons). Score plafonné entre 0 et 100."""
        malus = 0
        reasons: list[str] = []

        # Reachability
        if not twin.reachable:
            malus += HEALTH_RULES["unreachable"]
            reasons.append("Équipement injoignable")

        # Heartbeat
        if device and device.last_heartbeat_at:
            age = (timezone.now() - device.last_heartbeat_at).total_seconds()
            if age > 3600:
                malus += HEALTH_RULES["heartbeat_stale_1h"]
                reasons.append(f"Heartbeat > 1h ({int(age // 60)} min)")
            elif age > 300:
                malus += HEALTH_RULES["heartbeat_stale_5min"]
                reasons.append(f"Heartbeat > 5 min ({int(age // 60)} min)")
        elif device and not device.last_heartbeat_at and twin.last_probed_at:
            # Jamais de heartbeat mais device connu → warning léger
            reasons.append("Aucun heartbeat reçu")

        # Batterie
        b = twin.battery_percent
        if b is not None:
            if b < 10:
                malus += HEALTH_RULES["battery_below_10"]
                reasons.append(f"Batterie critique ({b}%)")
            elif b < 20:
                malus += HEALTH_RULES["battery_below_20"]
                reasons.append(f"Batterie faible ({b}%)")

        # Température
        t = twin.temperature_c
        if t is not None:
            if t >= 75:
                malus += HEALTH_RULES["temp_above_75"]
                reasons.append(f"Température critique ({t:.1f}°C)")
            elif t >= 60:
                malus += HEALTH_RULES["temp_above_60"]
                reasons.append(f"Température élevée ({t:.1f}°C)")

        # CPU
        c = twin.cpu_percent
        if c is not None:
            if c >= 95:
                malus += HEALTH_RULES["cpu_above_95"]
                reasons.append(f"CPU saturé ({c:.0f}%)")
            elif c >= 80:
                malus += HEALTH_RULES["cpu_above_80"]
                reasons.append(f"CPU élevé ({c:.0f}%)")

        # RAM
        r = twin.ram_percent
        if r is not None and r >= 85:
            malus += HEALTH_RULES["ram_above_85"]
            reasons.append(f"RAM saturée ({r:.0f}%)")

        # Storage
        s = twin.storage_percent
        if s is not None:
            if s >= 95:
                malus += HEALTH_RULES["storage_above_95"]
                reasons.append(f"Stockage critique ({s:.0f}%)")
            elif s >= 85:
                malus += HEALTH_RULES["storage_above_85"]
                reasons.append(f"Stockage élevé ({s:.0f}%)")

        # Latence
        if twin.latency_ms and twin.latency_ms > 1000:
            malus += HEALTH_RULES["latency_high"]
            reasons.append(f"Latence élevée ({twin.latency_ms} ms)")

        # Erreurs récentes (dernière heure)
        if twin.recent_errors:
            recent = [e for e in twin.recent_errors
                      if e.get("at", "") > (timezone.now() - timedelta(hours=1)).isoformat()]
            if len(recent) >= 3:
                malus += HEALTH_RULES["recent_errors"]
                reasons.append(f"{len(recent)} erreurs récentes")

        score = max(0, min(100, 100 - malus))
        return score, reasons

    # ────────────────────────────────────────────────────────────
    # Batch refresh
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def refresh_batch(devices, use_driver: bool = True) -> dict:
        """Refresh tous les twins d'une liste de devices. Retourne stats."""
        ok, ko = 0, 0
        for d in devices:
            try:
                TwinService.refresh(d, use_driver=use_driver)
                ok += 1
            except Exception as exc:
                logger.exception("Twin refresh KO device=%s : %s", d.pk, exc)
                ko += 1
        return {"ok": ok, "ko": ko}


def _append_error(twin, message: str):
    """Ring buffer d'erreurs (max 20)."""
    entry = {"at": timezone.now().isoformat(), "msg": str(message)[:240]}
    errors = list(twin.recent_errors or [])
    errors.append(entry)
    twin.recent_errors = errors[-20:]
