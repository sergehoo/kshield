"""Notifications déclenchées par les events Shield.

Branche les signaux post_save sur AccessEvent + FraudAlert pour générer
les notifications appropriées (retard, refus carte, alerte fraude).

Règles métier :
  - Refus de carte (`decision='denied'`) → notif aux admins du site
  - Pointage très tardif (> 45 min après morning_start) → notif manager
  - FraudAlert créée → notif équipe sécu
  - Heartbeat device manquant > 10 min → notif tech

Pour activer/désactiver : ``NOTIFICATIONS_AUTO_ENABLED`` dans settings.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return getattr(settings, "NOTIFICATIONS_AUTO_ENABLED", True)


# ─────────────────────────────────────────────────────────────────────────────
# AccessEvent → notif refus carte
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender="access_control.AccessEvent")
def _on_access_event(sender, instance, created, **kwargs):
    if not created or not _enabled():
        return

    # Refus de carte → notif aux admins du site (service existant)
    if instance.decision == "denied":
        try:
            from .services import notify_access_denied
            notify_access_denied(instance)
        except Exception:
            logger.exception("notify_access_denied failed for event %s", instance.pk)
        return

    # Pointage très tardif → notif manager (si manager défini sur l'employé)
    if instance.decision == "granted" and instance.direction == "in":
        try:
            _notify_if_late(instance)
        except Exception:
            logger.exception("late notif failed for event %s", instance.pk)


def _notify_if_late(event) -> None:
    """Crée une notif si le pointage est très en retard (>45 min)."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    from .models import Notification

    # Heure standard d'arrivée (8h00 par défaut) — paramétrable par site
    site = event.site
    params = {"morning_start": time(8, 0), "very_late_min": 45}
    if site and isinstance(getattr(site, "spec", None), dict):
        att = site.spec.get("attendance", {}) or {}
        try:
            params["morning_start"] = time.fromisoformat(str(att.get("morning_start", "08:00")))
        except Exception:
            pass
        try:
            params["very_late_min"] = int(att.get("very_late_tolerance_min", 45))
        except Exception:
            pass

    morning = datetime.combine(
        event.timestamp.date(), params["morning_start"],
        tzinfo=event.timestamp.tzinfo,
    )
    delay_min = int((event.timestamp - morning).total_seconds() // 60)
    if delay_min <= params["very_late_min"]:
        return

    holder = None
    try:
        holder = event.holder_content_type.get_object_for_this_type(
            pk=event.holder_object_id,
        )
    except Exception:
        return

    name = f"{getattr(holder, 'first_name', '')} {getattr(holder, 'last_name', '')}".strip()
    manager = getattr(holder, "manager", None)
    if not manager:
        return    # pas de manager, on ne notifie pas

    Notification.objects.create(
        tenant=event.tenant,
        recipient=manager.user if hasattr(manager, "user") else None,
        channel="email",
        subject=f"⏰ Pointage tardif : {name}",
        body=(
            f"{name} a pointé à {event.timestamp:%H:%M} sur le site "
            f"{event.site.name if event.site else '?'}, soit {delay_min} minutes "
            f"après l'heure de référence ({params['morning_start']:%H:%M})."
        ),
        payload={
            "event_id": str(event.uuid),
            "delay_minutes": delay_min,
            "site": event.site.name if event.site else None,
        },
        status="queued",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FraudAlert → notif équipe sécu
# ─────────────────────────────────────────────────────────────────────────────
try:
    from antifraud.models import FraudAlert

    @receiver(post_save, sender=FraudAlert)
    def _on_fraud_alert(sender, instance, created, **kwargs):
        if not created or not _enabled():
            return
        try:
            from .services import notify_fraud_alert
            notify_fraud_alert(instance)
        except Exception:
            logger.exception("notify_fraud_alert failed for alert %s", instance.pk)
except Exception:
    pass
