"""KAYDAN SHIELD — Évaluation des règles anti-fraude pour un AccessEvent.

Le moteur est intentionnellement simple : chaque règle a un code unique,
référencé dans des handlers Python. Quand `evaluate(event)` est appelé,
on parcourt les FraudRule actives et on appelle le handler correspondant
au code. Si le handler renvoie `True`, on crée une FraudAlert.

Codes implémentés :
    BADGE_LOAN          Le badge a été utilisé par 2 holders distincts
                        sur la même journée.
    BADGE_TWICE_IN      Plusieurs entrées consécutives sans sortie sur le
                        même site dans les 60 minutes (badge prêté).
    OUT_OF_HOURS        Scan en dehors des plages horaires autorisées
                        (rule.parameters = {"start": "06:00", "end": "20:00"}).
    GHOST_HELMET        Casque scanné sans badge associé (chantier).
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
    if event.helmet_uid and not event.badge_uid:
        return {"helmet_uid": event.helmet_uid, "site_id": event.site_id}
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
