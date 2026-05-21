"""KAYDAN SHIELD — Tâches Celery core (gauges Prometheus + housekeeping)."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="core.refresh_prometheus_gauges")
def refresh_prometheus_gauges() -> dict:
    """Met à jour les gauges Prometheus business (~30s d'intervalle).

    À planifier dans Celery Beat :
        - task: core.refresh_prometheus_gauges
        - schedule: every 30 seconds
    """
    try:
        from core.metrics import refresh_gauges
        refresh_gauges()
        return {"status": "ok"}
    except Exception:
        logger.exception("refresh_prometheus_gauges a échoué")
        return {"status": "error"}
