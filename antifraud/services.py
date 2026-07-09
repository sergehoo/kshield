"""KAYDAN SHIELD — Évaluation des règles anti-fraude pour un AccessEvent.

Le moteur est intentionnellement simple : chaque règle a un code unique,
référencé dans des handlers Python. Quand `evaluate(event)` est appelé,
on parcourt les FraudRule actives et on appelle le handler correspondant
au code. Si le handler renvoie `True`, on crée une FraudAlert.

Codes implémentés :
    BADGE_LOAN              Le badge a été utilisé par 2 holders distincts
                            sur la même journée.
    BADGE_TWICE_IN          Plusieurs entrées consécutives sans sortie sur le
                            même site dans les 60 minutes (badge prêté).
    OUT_OF_HOURS            Scan en dehors des plages horaires autorisées
                            (rule.parameters = {"start": "06:00", "end": "20:00"}).
    GHOST_HELMET            Casque scanné sans badge associé (chantier).
    BADGE_WITHOUT_HELMET    Badge ouvrier scanné sans casque couplé (sécurité
                            BTP — un ouvrier sur chantier doit porter son
                            casque BLE pour être tracké).
    OUTSIDE_GEOFENCE        Scan hors du polygone géographique du site.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Iterable

from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers — chaque fonction reçoit (event, rule) et retourne un dict
# `evidence` si la règle se déclenche, sinon None.
# ---------------------------------------------------------------------------
def _handler_badge_loan(event, rule) -> dict | None:
    if not event.badge_uid or not event.holder_object_id:
        return None
    from django.db.models import Q

    from access_control.models import AccessEvent
    today = timezone.localtime(event.timestamp).date()
    qs = (AccessEvent.objects
          .filter(badge_uid=event.badge_uid, timestamp__date=today)
          .exclude(id=event.id))
    # Un autre holder = même badge_uid mais (holder_kind, holder_id) différents
    other = qs.exclude(
        Q(holder_kind=event.holder_kind, holder_object_id=event.holder_object_id),
    ).first()
    if other:
        return {"badge_uid": event.badge_uid,
                "first_holder_id": other.holder_object_id,
                "first_holder_kind": other.holder_kind,
                "first_seen_at": other.timestamp.isoformat()}
    return None


def _handler_badge_twice_in(event, rule) -> dict | None:
    if event.direction != "in" or not event.badge_uid:
        return None
    from access_control.models import AccessEvent
    window = timedelta(minutes=int(rule.parameters.get("window_min", 60))) if rule.parameters else timedelta(minutes=60)
    since = event.timestamp - window
    prior = (AccessEvent.objects
             .filter(badge_uid=event.badge_uid, direction="in",
                     site_id=event.site_id, timestamp__gte=since)
             .exclude(id=event.id)
             .exists())
    out_between = (AccessEvent.objects
                   .filter(badge_uid=event.badge_uid, direction="out",
                           site_id=event.site_id, timestamp__gte=since)
                   .exists())
    if prior and not out_between:
        return {"badge_uid": event.badge_uid, "site_id": event.site_id,
                "window_min": int(window.total_seconds() // 60)}
    return None


def _handler_out_of_hours(event, rule) -> dict | None:
    if not rule.parameters:
        return None
    try:
        start = time.fromisoformat(rule.parameters.get("start", "06:00"))
        end = time.fromisoformat(rule.parameters.get("end", "20:00"))
    except ValueError:
        return None
    local = timezone.localtime(event.timestamp).time()
    if start <= local <= end:
        return None
    return {"scan_time": local.isoformat(), "allowed_window": f"{start}-{end}"}


def _handler_ghost_helmet(event, rule) -> dict | None:
    """Casque détecté SANS badge → quelqu'un a un casque mais pas badgé."""
    if event.helmet_uid and not event.badge_uid:
        return {"helmet_uid": event.helmet_uid, "site_id": event.site_id}
    return None


def _handler_badge_without_helmet(event, rule) -> dict | None:
    """Badge ouvrier scanné SANS casque couplé → ouvrier sur chantier non tracké.

    Risque sécurité BTP : un ouvrier sans casque ne peut pas être détecté
    par les beacons BLE en cas d'immobilité (malaise, chute, etc.) → alerte
    obligatoire à acquitter par le superviseur.
    """
    if (event.holder_kind == "worker"
            and event.badge_uid
            and not event.helmet_uid):
        return {
            "badge_uid": event.badge_uid,
            "holder_id": event.holder_object_id,
            "site_id": event.site_id,
            "denial_reason": event.denial_reason,
        }
    return None


def _handler_outside_geofence(event, rule) -> dict | None:
    """Le scan a été géolocalisé hors du polygone du site.
    Nécessite que le terminal envoie latitude/longitude dans le payload.
    """
    if event.latitude is None or event.longitude is None or not event.site_id:
        return None
    try:
        from sites.geofence import site_contains_point
        inside = site_contains_point(event.site, event.latitude, event.longitude)
    except Exception:
        return None
    if inside is False:  # None = pas de polygone, on n'alerte pas
        return {
            "site_id": event.site_id,
            "latitude": float(event.latitude),
            "longitude": float(event.longitude),
        }
    return None


HANDLERS = {
    "BADGE_LOAN": _handler_badge_loan,
    "BADGE_TWICE_IN": _handler_badge_twice_in,
    "OUT_OF_HOURS": _handler_out_of_hours,
    "GHOST_HELMET": _handler_ghost_helmet,
    "BADGE_WITHOUT_HELMET": _handler_badge_without_helmet,
    "OUTSIDE_GEOFENCE": _handler_outside_geofence,
}


def evaluate(event) -> list:
    """Évalue toutes les règles actives pour un AccessEvent.
    Retourne la liste des FraudAlert créées.
    """
    from antifraud.models import FraudAlert, FraudRule

    qs = FraudRule.objects.filter(is_active=True)
    if event.tenant_id:
        qs = qs.filter(tenant_id=event.tenant_id)

    created = []
    for rule in qs:
        handler = HANDLERS.get(rule.code)
        if not handler:
            continue
        try:
            evidence = handler(event, rule)
        except Exception:
            logger.exception("FraudRule handler %s a échoué pour event=%s", rule.code, event.id)
            continue
        if not evidence:
            continue

        alert = FraudAlert.objects.create(
            tenant_id=event.tenant_id,
            rule=rule,
            site_id=event.site_id,
            raised_at=timezone.now(),
            primary_holder_kind=event.holder_kind or "",
            primary_holder_id=event.holder_object_id,
            related_event=event,
            severity=rule.severity,
            status="open",
            evidence=evidence,
        )
        created.append(alert)
        logger.info("FraudAlert #%s déclenchée — règle %s sur event=%s",
                    alert.id, rule.code, event.id)
    return created


# ═══════════════════════════════════════════════════════════════════
# Vague 10 — Nouvelles règles anti-fraude
# ═══════════════════════════════════════════════════════════════════
def _handler_badge_expired(event, rule) -> dict | None:
    """BADGE_EXPIRED — le badge scanné est expiré (valid_until dépassé)."""
    if not event.badge_id:
        return None
    from devices.models import Badge
    try:
        badge = Badge.objects.get(pk=event.badge_id)
    except Badge.DoesNotExist:
        return None
    from datetime import date
    today = date.today()
    if badge.valid_until and badge.valid_until < today:
        return {
            "badge_id": badge.pk, "uid": badge.uid,
            "valid_until": badge.valid_until.isoformat(),
            "days_expired": (today - badge.valid_until).days,
        }
    if badge.status in ("expired", "revoked", "lost", "disabled"):
        return {"badge_id": badge.pk, "uid": badge.uid, "status": badge.status}
    return None


def _handler_multi_site_conflict(event, rule) -> dict | None:
    """MULTI_SITE_CONFLICT — un même holder scanné sur 2 sites incompatibles
    dans une fenêtre de temps où le déplacement est physiquement impossible.

    Paramètre rule.parameters = {"min_travel_minutes": 30}
    """
    if not event.holder_object_id or not event.site_id:
        return None
    from access_control.models import AccessEvent
    min_travel = (rule.parameters or {}).get("min_travel_minutes", 30)
    since = event.timestamp - timedelta(minutes=min_travel)
    conflict = AccessEvent.objects.filter(
        holder_kind=event.holder_kind,
        holder_object_id=event.holder_object_id,
        timestamp__gte=since,
        timestamp__lt=event.timestamp,
        decision="granted",
    ).exclude(site_id=event.site_id).first()
    if conflict:
        return {
            "current_site_id": event.site_id,
            "conflict_site_id": conflict.site_id,
            "conflict_event_id": conflict.id,
            "gap_seconds": int(
                (event.timestamp - conflict.timestamp).total_seconds()
            ),
        }
    return None


def _handler_repeated_absence(event, rule) -> dict | None:
    """REPEATED_ABSENCE — plus de N absences sur les X derniers jours ouvrés.

    Paramètres : {"days": 30, "threshold": 5}
    Se déclenche lorsqu'un holder scanne après une période d'absences.
    """
    if not event.holder_object_id:
        return None
    params = rule.parameters or {}
    days = int(params.get("days", 30))
    threshold = int(params.get("threshold", 5))
    try:
        from attendance.models import AttendanceDay
    except ImportError:
        return None
    since = event.timestamp.date() - timedelta(days=days)
    absences = AttendanceDay.objects.filter(
        date__gte=since, date__lt=event.timestamp.date(),
        status="absent",
    )
    if event.holder_kind == "worker":
        absences = absences.filter(worker_id=event.holder_object_id)
    elif event.holder_kind == "employee":
        absences = absences.filter(employee_id=event.holder_object_id)
    else:
        return None
    count = absences.count()
    if count >= threshold:
        return {"absences_last_days": count, "days_window": days,
                 "threshold": threshold}
    return None


def _handler_frequent_late(event, rule) -> dict | None:
    """FREQUENT_LATE — plus de N retards sur les X derniers jours ouvrés."""
    if not event.holder_object_id:
        return None
    params = rule.parameters or {}
    days = int(params.get("days", 30))
    threshold = int(params.get("threshold", 5))
    try:
        from attendance.models import AttendanceDay
    except ImportError:
        return None
    since = event.timestamp.date() - timedelta(days=days)
    lates = AttendanceDay.objects.filter(
        date__gte=since, date__lt=event.timestamp.date(),
        status="late",
    )
    if event.holder_kind == "worker":
        lates = lates.filter(worker_id=event.holder_object_id)
    elif event.holder_kind == "employee":
        lates = lates.filter(employee_id=event.holder_object_id)
    else:
        return None
    count = lates.count()
    if count >= threshold:
        return {"lates_last_days": count, "days_window": days,
                 "threshold": threshold}
    return None


def _handler_suspicious_terminal(event, rule) -> dict | None:
    """SUSPICIOUS_TERMINAL — terminal avec un taux d'erreurs anormalement
    élevé (health score < seuil OU >N erreurs récentes).

    Paramètres : {"health_score_below": 40, "errors_last_hour": 10}
    """
    if not event.device_id:
        return None
    from devices.models import DeviceTwin
    params = rule.parameters or {}
    score_threshold = int(params.get("health_score_below", 40))
    errors_threshold = int(params.get("errors_last_hour", 10))
    try:
        twin = DeviceTwin.objects.get(device_id=event.device_id)
    except DeviceTwin.DoesNotExist:
        return None
    if twin.health_score < score_threshold:
        return {
            "device_id": event.device_id, "health_score": twin.health_score,
            "reason": "health_score_below_threshold",
            "threshold": score_threshold,
        }
    now = timezone.now()
    recent_errors = [
        e for e in (twin.recent_errors or [])
        if e.get("at", "") > (now - timedelta(hours=1)).isoformat()
    ]
    if len(recent_errors) >= errors_threshold:
        return {
            "device_id": event.device_id,
            "errors_last_hour": len(recent_errors),
            "threshold": errors_threshold,
        }
    return None


def _handler_abnormal_access(event, rule) -> dict | None:
    """ABNORMAL_ACCESS — accès qui dévie fortement du pattern habituel du
    holder (horaire inhabituel, jour de la semaine inhabituel, site jamais visité).

    Paramètres : {"lookback_days": 90, "min_history": 20}
    """
    if not event.holder_object_id:
        return None
    from access_control.models import AccessEvent
    params = rule.parameters or {}
    lookback = int(params.get("lookback_days", 90))
    min_history = int(params.get("min_history", 20))
    since = event.timestamp - timedelta(days=lookback)
    history = AccessEvent.objects.filter(
        holder_kind=event.holder_kind,
        holder_object_id=event.holder_object_id,
        timestamp__gte=since, timestamp__lt=event.timestamp,
        decision="granted",
    )
    hist_count = history.count()
    if hist_count < min_history:
        return None  # pas assez d'historique pour juger
    # Site jamais visité ?
    visited_sites = set(history.values_list("site_id", flat=True))
    if event.site_id and event.site_id not in visited_sites:
        return {"reason": "unseen_site", "site_id": event.site_id,
                 "visited_sites": list(visited_sites)}
    # Heure inhabituelle : hors du min-max habituel ± 2h
    from django.db.models import Max, Min
    hours = list(history.values_list("timestamp", flat=True))
    hour_now = event.timestamp.hour
    hours_of_day = sorted({h.hour for h in hours})
    if hours_of_day:
        min_h, max_h = hours_of_day[0], hours_of_day[-1]
        if hour_now < max(0, min_h - 2) or hour_now > min(23, max_h + 2):
            return {"reason": "unusual_hour", "hour": hour_now,
                     "usual_range": [min_h, max_h]}
    # Jour de semaine inhabituel (uniquement si historique riche)
    weekday_now = event.timestamp.weekday()
    weekdays = {h.weekday() for h in hours}
    if hist_count >= 40 and weekday_now not in weekdays:
        return {"reason": "unusual_weekday", "weekday": weekday_now,
                 "usual_weekdays": sorted(weekdays)}
    return None


def _handler_device_tampered(event, rule) -> dict | None:
    """DEVICE_TAMPERED — équipement dont l'IP a changé, ou marqué en maintenance,
    ou hors de son site attendu.
    """
    if not event.device_id:
        return None
    from devices.models import Device
    try:
        device = Device.objects.get(pk=event.device_id)
    except Device.DoesNotExist:
        return None
    reasons = []
    if device.status in ("maintenance", "lost"):
        reasons.append(f"device_status={device.status}")
    # Event émis alors que device.site_id != event.site_id → suspect
    if device.site_id and event.site_id and device.site_id != event.site_id:
        reasons.append(f"site_mismatch device={device.site_id} event={event.site_id}")
    if reasons:
        return {"device_id": device.pk, "serial": device.serial_number,
                 "reasons": reasons}
    return None


# ═══════════════════════════════════════════════════════════════════
# Enregistrement des nouveaux handlers
# ═══════════════════════════════════════════════════════════════════
HANDLERS.update({
    "BADGE_EXPIRED":       _handler_badge_expired,
    "MULTI_SITE_CONFLICT": _handler_multi_site_conflict,
    "REPEATED_ABSENCE":    _handler_repeated_absence,
    "FREQUENT_LATE":       _handler_frequent_late,
    "SUSPICIOUS_TERMINAL": _handler_suspicious_terminal,
    "ABNORMAL_ACCESS":     _handler_abnormal_access,
    "DEVICE_TAMPERED":     _handler_device_tampered,
})
