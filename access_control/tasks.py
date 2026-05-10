"""KAYDAN SHIELD — Tâches Celery du pipeline d'accès.

`dispatch_access_event` est appelée après chaque scan réussi pour :
1. évaluer toutes les règles anti-fraude actives,
2. déclencher les notifications (alertes ouvertes + accès refusés sensibles),
3. propager l'événement aux consumers WebSocket pour le flux temps réel.

En dev, `CELERY_TASK_ALWAYS_EAGER=True` => exécution synchrone (pratique pour
les tests et le smoke local). En prod, c'est un broker Redis qui prend.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="access_control.dispatch_access_event")
def dispatch_access_event(event_id: int) -> dict:
    """Évalue les règles anti-fraude + envoie les notifications pour un AccessEvent."""
    from access_control.models import AccessEvent
    try:
        event = AccessEvent.objects.select_related("site", "device").get(pk=event_id)
    except AccessEvent.DoesNotExist:
        logger.warning("AccessEvent #%s introuvable — dispatch annulé", event_id)
        return {"event_id": event_id, "status": "missing"}

    # 1. anti-fraude
    alerts_created = []
    try:
        from antifraud.services import evaluate
        alerts = evaluate(event)
        alerts_created = [a.id for a in alerts]
    except Exception:
        logger.exception("Échec évaluation anti-fraude pour event=%s", event_id)

    # 2. notifications
    notif_count = 0
    try:
        from notifications.services import (notify_access_denied,
                                              notify_fraud_alert)
        for alert_id in alerts_created:
            from antifraud.models import FraudAlert
            try:
                alert = FraudAlert.objects.get(pk=alert_id)
                notif_count += notify_fraud_alert(alert)
            except FraudAlert.DoesNotExist:
                pass
        # Notifier aussi un accès refusé même sans alerte fraude
        if event.decision == "denied":
            notif_count += notify_access_denied(event)
    except Exception:
        logger.exception("Échec dispatch notifications pour event=%s", event_id)

    # 3. WebSocket — best-effort
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)("realtime-events", {
                "type": "access.event",
                "event_id": event.id,
                "decision": event.decision,
            })
    except Exception:
        logger.debug("Pas de WebSocket layer — broadcast skip", exc_info=True)

    return {"event_id": event_id, "alerts": alerts_created,
            "notifications": notif_count}
