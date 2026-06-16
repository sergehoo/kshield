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


# ─────────────────────────────────────────────────────────────────────────────
# Agrégation AccessEvent → Punch → AttendanceDay (déclenchée toutes les 5 min)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

_PUNCH_DEFAULTS = {
    "morning_start":         time(8, 0),
    "late_tolerance_min":    15,
    "very_late_tolerance_min": 45,
    "break_window_start":    time(12, 0),
    "break_window_end":      time(14, 0),
    "min_duration_present":  4 * 60,   # 4h
    "min_duration_partial":  1 * 60,   # 1h
}


def _site_params(site):
    """Récupère les paramètres d'attendance pour un site (Site.spec.attendance)."""
    params = dict(_PUNCH_DEFAULTS)
    if site and isinstance(getattr(site, "spec", None), dict):
        custom = site.spec.get("attendance", {}) or {}
        for k in ("morning_start", "break_window_start", "break_window_end"):
            if k in custom:
                try: params[k] = time.fromisoformat(str(custom[k]))
                except Exception: pass
        for k in ("late_tolerance_min", "very_late_tolerance_min",
                  "min_duration_present", "min_duration_partial"):
            if k in custom:
                try: params[k] = int(custom[k])
                except Exception: pass
    return params


def _classify_punch_type(ts, params, prev_type):
    """morning_in / break_out / break_in / evening_out."""
    t = ts.time()
    in_break_window = params["break_window_start"] <= t <= params["break_window_end"]
    if prev_type is None:
        return "morning_in"
    if prev_type == "morning_in" and in_break_window:
        return "break_out"
    if prev_type == "break_out" and in_break_window:
        return "break_in"
    if prev_type in ("morning_in", "break_in", "break_out"):
        return "evening_out"
    return "morning_in"


def _classify_late(ts, params):
    """Pour un punch d'entrée matin : (status, delay_minutes)."""
    morning = datetime.combine(ts.date(), params["morning_start"], tzinfo=ts.tzinfo)
    diff = int((ts - morning).total_seconds() // 60)
    if diff <= 0:                                  return "on_time", 0
    if diff <= params["late_tolerance_min"]:       return "on_time", diff
    if diff <= params["very_late_tolerance_min"]:  return "late", diff
    return "very_late", diff


def _classify_day_status(duration_min, params):
    if duration_min >= params["min_duration_present"]:  return "present"
    if duration_min >= params["min_duration_partial"]:  return "partial"
    return "absent"


@shared_task(name="attendance.aggregate_punches",
             autoretry_for=(Exception,),
             retry_kwargs={"max_retries": 2, "countdown": 60})
def aggregate_punches(days_back: int = 2) -> dict:
    """Transforme les AccessEvent récents en Punch + AttendanceDay.

    Args:
        days_back: nb de jours en arrière à rejouer (default 2 — rattrape les
            events arrivés en retard via la sync ZKTeco). Idempotent grâce à
            ``source_event`` (FK unique vers AccessEvent).

    Returns:
        {"punches_created": N, "days_updated": M, "errors": [...]}
    """
    from access_control.models import AccessEvent
    from attendance.models import AttendanceDay, Punch

    cutoff = timezone.now() - timedelta(days=days_back, hours=2)
    events = (AccessEvent.objects
              .filter(timestamp__gte=cutoff,
                      decision="granted",
                      holder_object_id__isnull=False)
              .exclude(holder_kind="unknown")
              .select_related("site")
              .order_by("holder_kind", "holder_object_id", "timestamp"))

    punches_created = 0
    days_updated = 0
    errors = []
    current_key = None
    current_events = []

    def _flush(key, group_events):
        nonlocal punches_created, days_updated
        if not group_events:
            return
        site = group_events[0].site
        if not site:
            return
        tenant = group_events[0].tenant
        holder_kind = group_events[0].holder_kind
        holder_id = group_events[0].holder_object_id
        day_date = group_events[0].timestamp.astimezone().date()
        params = _site_params(site)

        with transaction.atomic():
            prev_type = None
            # Hydrate prev_type depuis d'éventuels punches déjà créés ce jour
            last_punch = (Punch.objects.filter(
                tenant=tenant, site=site,
                holder_kind=holder_kind, holder_object_id=holder_id,
                timestamp__date=day_date,
            ).order_by("-timestamp").first())
            if last_punch:
                prev_type = last_punch.type

            for ev in group_events:
                if Punch.objects.filter(source_event=ev).exists():
                    continue
                punch_type = _classify_punch_type(ev.timestamp, params, prev_type)
                if punch_type == "morning_in":
                    status_, delay = _classify_late(ev.timestamp, params)
                else:
                    status_, delay = "on_time", 0
                Punch.objects.create(
                    tenant=tenant, site=site,
                    holder_kind=holder_kind,
                    holder_content_type=ev.holder_content_type,
                    holder_object_id=ev.holder_object_id,
                    type=punch_type, status=status_,
                    timestamp=ev.timestamp, delay_minutes=delay,
                    source_event=ev,
                )
                punches_created += 1
                prev_type = punch_type

            # Recalcul AttendanceDay
            day_punches = (Punch.objects.filter(
                tenant=tenant, site=site,
                holder_kind=holder_kind, holder_object_id=holder_id,
                timestamp__date=day_date,
            ).order_by("timestamp"))
            if not day_punches.exists():
                return

            first = day_punches.first().timestamp
            last = day_punches.last().timestamp
            duration = max(0, int((last - first).total_seconds() // 60)) if last > first else 0
            # Pause midi déduite
            bo = day_punches.filter(type="break_out").first()
            bi = day_punches.filter(type="break_in").first()
            if bo and bi and bi.timestamp > bo.timestamp:
                duration -= int((bi.timestamp - bo.timestamp).total_seconds() // 60)
            duration = max(0, duration)

            total_delay = sum(p.delay_minutes for p in day_punches if p.delay_minutes > 0)
            status_d = _classify_day_status(duration, params)

            AttendanceDay.objects.update_or_create(
                tenant=tenant, site=site,
                holder_kind=holder_kind, holder_object_id=holder_id,
                date=day_date,
                defaults={
                    "status": status_d,
                    "first_punch_at": first,
                    "last_punch_at": last,
                    "duration_minutes": duration,
                    "delay_total_minutes": total_delay,
                },
            )
            days_updated += 1

    for ev in events:
        site_id = ev.site_id or 0
        day_d = ev.timestamp.astimezone().date()
        key = (ev.tenant_id, site_id, ev.holder_kind, ev.holder_object_id, day_d)
        if key != current_key:
            if current_key is not None:
                try:    _flush(current_key, current_events)
                except Exception as exc:
                    logger.exception("aggregate_punches flush failed")
                    errors.append({"group": str(current_key), "error": str(exc)[:200]})
            current_key = key
            current_events = []
        current_events.append(ev)
    if current_events:
        try:    _flush(current_key, current_events)
        except Exception as exc:
            errors.append({"group": str(current_key), "error": str(exc)[:200]})

    return {"punches_created": punches_created,
            "days_updated": days_updated,
            "errors": errors,
            "days_back": days_back}
