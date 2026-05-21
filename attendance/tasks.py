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


@shared_task(name="attendance.reconcile_face_presence_today")
def reconcile_face_presence_today() -> dict:
    """Job de fin de journée : marque les badges sans face comme 'badge_only'.

    Planifier en Celery beat ~21h (après l'heure max de départ). Crée des
    FaceCheckinConfirmation `status='badge_only'` pour tous les Punches
    d'employés qui n'ont pas été vus par une caméra.
    """
    from attendance.services_face import reconcile_badge_only_today
    try:
        created = reconcile_badge_only_today()
    except Exception:
        logger.exception("reconcile_face_presence_today a échoué")
        return {"status": "error"}
    return {"status": "ok", "badge_only_created": created}


@shared_task(name="attendance.ingest_ble_batch", bind=True, max_retries=3,
              default_retry_delay=10)
def ingest_ble_batch(self, pings: list[dict]) -> dict:
    """Insère un batch de pings BLE en bulk (async pour ne pas bloquer l'edge).

    Appelé par BLEPresencePingViewSet.batch_ingest quand la queue dépasse 200
    ou que ``async=true`` est passé en query string. La task fait ses propres
    retries Celery avec backoff exponentiel — robuste aux pertes Postgres.
    """
    from attendance.models import BLEPresencePing
    from devices.models import Helmet
    if not pings:
        return {"ingested": 0, "skipped": 0}

    uids = {p.get("helmet_uid") for p in pings if p.get("helmet_uid")}
    helmets = {h.uhf_tag_uid: h for h in Helmet.objects.filter(uhf_tag_uid__in=uids)}

    objects = []
    skipped = 0
    for p in pings:
        helmet = helmets.get(p.get("helmet_uid"))
        if not helmet:
            skipped += 1
            continue
        objects.append(BLEPresencePing(
            helmet=helmet,
            timestamp=p.get("timestamp"),
            rssi=p.get("rssi"),
            is_immobile=bool(p.get("is_immobile", False)),
            accelerometer_payload=p.get("accelerometer_payload") or {},
        ))
    try:
        BLEPresencePing.objects.bulk_create(objects, batch_size=500)
    except Exception as exc:
        logger.exception("ingest_ble_batch a échoué — retry %s", self.request.retries)
        raise self.retry(exc=exc) from exc
    return {"ingested": len(objects), "skipped": skipped}
