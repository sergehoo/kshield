"""KAYDAN SHIELD — Tâches Celery du pointage.

À planifier via django-celery-beat :

    Schedule "BLE rollup":
        Task: attendance.tasks.ble_rollup_and_evaluate
        Cron : */5 * * * *   (toutes les 5 min)
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="attendance.ble_rollup_and_evaluate")
def ble_rollup_and_evaluate() -> dict:
    """Roll-up des pings BLE → fenêtres 5 min, puis évaluation stillness."""
    from attendance.ble_stillness import evaluate_stillness, roll_up_windows
    try:
        windows = roll_up_windows(window_minutes=5)
    except Exception:
        logger.exception("BLE roll-up a échoué")
        windows = 0
    try:
        signals = evaluate_stillness()
    except Exception:
        logger.exception("Évaluation stillness a échoué")
        signals = []
    return {"windows_created": windows, "signals_created": [s.id for s in signals]}
