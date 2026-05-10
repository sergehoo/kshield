"""KAYDAN SHIELD — Dispatcher de notifications (in-app + email + push).

Stratégie : pour chaque déclencheur, on retrouve la liste des destinataires
(staff KAYDAN par défaut + utilisateurs avec préférence active sur le canal),
puis on crée une `Notification` par destinataire en statut `queued`. Les
adapters réels (SMTP, FCM, WebSocket) consomment la queue dans des tâches
Celery ou des workers Channels.

Cette factorisation reste minimale et best-effort : si un canal ou une table
manque, on log et on continue sans bloquer la pipeline d'accès.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _resolve_recipients(site=None):
    """Retourne le queryset des utilisateurs à notifier pour les alertes
    fraude/sécurité d'un site. Stratégie naïve mais correcte :
    tous les staff actifs (admins) + à terme les superviseurs liés au site.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    qs = User.objects.filter(is_active=True, is_staff=True)
    return qs


def notify_fraud_alert(alert) -> int:
    """Crée une Notification par destinataire pour une FraudAlert."""
    try:
        from notifications.models import Notification
    except Exception:
        logger.exception("Module notifications indisponible")
        return 0

    severity = (alert.severity or "medium").upper()
    rule_name = alert.rule.name if alert.rule_id else "Règle inconnue"
    site_name = alert.site.name if alert.site_id else "tous sites"

    subject = f"[{severity}] Alerte anti-fraude — {rule_name}"
    body = (
        f"Une alerte anti-fraude a été déclenchée sur {site_name}.\n"
        f"Règle : {rule_name}\n"
        f"Sévérité : {severity}\n"
        f"Porteur : {alert.primary_holder_kind} #{alert.primary_holder_id}\n"
        f"Détails : {alert.evidence}"
    )

    created = 0
    for user in _resolve_recipients(site=alert.site):
        try:
            Notification.objects.create(
                tenant_id=alert.tenant_id,
                recipient=user,
                channel="in_app",
                subject=subject,
                body=body,
                payload={"alert_id": alert.id, "rule": alert.rule.code if alert.rule_id else None},
                status="queued",
            )
            created += 1
        except Exception:
            logger.exception("Echec création Notification pour user=%s alert=%s",
                             user.id, alert.id)
    return created


def notify_access_denied(event) -> int:
    """Crée une notification quand un scan est refusé pour raison sensible
    (badge révoqué / casque manquant / hors-zone)."""
    if event.decision != "denied":
        return 0
    try:
        from notifications.models import Notification
    except Exception:
        return 0

    subject = f"Accès refusé — {event.denial_reason or 'inconnu'}"
    body = (
        f"Un accès a été refusé sur {event.site.name if event.site_id else '—'}.\n"
        f"Motif : {event.denial_reason}\n"
        f"Badge : {event.badge_uid or '—'} ({event.holder_kind or '—'})\n"
        f"Heure : {event.timestamp}"
    )
    created = 0
    for user in _resolve_recipients(site=event.site):
        try:
            Notification.objects.create(
                tenant_id=event.tenant_id,
                recipient=user,
                channel="in_app",
                subject=subject, body=body,
                payload={"event_id": event.id, "decision": event.decision,
                         "denial_reason": event.denial_reason},
                status="queued",
            )
            created += 1
        except Exception:
            logger.exception("Echec notif accès refusé pour event=%s", event.id)
    return created
