"""KAYDAN SHIELD — Dispatcher de notifications (in-app + email + push).

Stratégie : pour chaque déclencheur, on retrouve la liste des destinataires
(staff KAYDAN par défaut + utilisateurs avec préférence active sur le canal),
puis on crée une `Notification` par destinataire en statut `queued`. Si la
sévérité le justifie, on déclenche aussi un envoi email transactionnel via
`django.core.mail.send_mail` (config `EMAIL_BACKEND` + `DEFAULT_FROM_EMAIL`).

Cette factorisation reste minimale et best-effort : si un canal ou une table
manque, on log et on continue sans bloquer la pipeline d'accès.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def _send_email_transactional(notification, immediate: bool = True) -> bool:
    """Envoie un email pour une Notification déjà créée. Met à jour son status."""
    if not notification.recipient or not notification.recipient.email:
        return False
    try:
        sent = send_mail(
            subject=notification.subject or "[KAYDAN SHIELD]",
            message=notification.body or "",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                 "no-reply@kaydangroupe.com"),
            recipient_list=[notification.recipient.email],
            fail_silently=False,
        )
        if sent:
            notification.status = "sent"
            notification.sent_at = timezone.now()
            notification.save(update_fields=["status", "sent_at"])
            return True
    except Exception as exc:
        notification.status = "failed"
        notification.failure_reason = str(exc)[:200]
        notification.save(update_fields=["status", "failure_reason"])
        logger.warning("Échec envoi email pour notif=%s : %s",
                       notification.id, exc)
    return False


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

    # Envoie aussi un email pour les alertes critiques/élevées
    should_email = (alert.severity or "").lower() in ("critical", "high")

    created = 0
    for user in _resolve_recipients(site=alert.site):
        try:
            n = Notification.objects.create(
                tenant_id=alert.tenant_id,
                recipient=user,
                channel="in_app",
                subject=subject,
                body=body,
                payload={"alert_id": alert.id, "rule": alert.rule.code if alert.rule_id else None},
                status="queued",
            )
            created += 1
            if should_email and user.email:
                # Crée également une notif email duplicate
                email_n = Notification.objects.create(
                    tenant_id=alert.tenant_id,
                    recipient=user, channel="email",
                    subject=subject, body=body,
                    payload={"alert_id": alert.id},
                    status="queued",
                )
                _send_email_transactional(email_n)
        except Exception:
            logger.exception("Echec création Notification pour user=%s alert=%s",
                             user.id, alert.id)
    return created


def notify_visit_status_change(visit_request, new_status: str) -> int:
    """Notifie l'hôte employé + visiteur (par email) d'un changement de statut.

    Statuts qui déclenchent un email :
        - approved  → email au visiteur avec lien check-in
        - rejected  → email au visiteur (poliment)
        - checked_in → notif in-app à l'hôte employé
    """
    try:
        from notifications.models import Notification
    except Exception:
        return 0

    sent = 0
    visitor = visit_request.visitor
    host = visit_request.host_employee
    site = visit_request.site

    # Si pas d'email mais téléphone, envoyer un SMS
    if new_status == "approved" and not getattr(visitor, "email", "") and getattr(visitor, "phone", ""):
        try:
            from notifications.sms import send_visit_qr_sms
            if send_visit_qr_sms(visit_request):
                sent += 1
        except Exception:
            logger.debug("SMS visite échoué", exc_info=True)

    if new_status == "approved" and getattr(visitor, "email", ""):
        n = Notification.objects.create(
            tenant_id=visit_request.tenant_id,
            recipient=None,  # destinataire externe (pas un User)
            channel="email",
            subject=f"Votre visite à KAYDAN — {site.name if site else ''} est confirmée",
            body=(f"Bonjour {visitor.first_name},\n\n"
                  f"Votre demande de visite est approuvée.\n"
                  f"Site : {site.name if site else '—'}\n"
                  f"Prévue le : {visit_request.scheduled_at}\n\n"
                  f"Présentez-vous à l'accueil avec une pièce d'identité.\n\n"
                  f"À bientôt,\nKAYDAN GROUPE"),
            payload={"visit_request_id": visit_request.id},
            status="queued",
        )
        # Email direct au visiteur
        try:
            send_mail(
                subject=n.subject, message=n.body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                     "no-reply@kaydangroupe.com"),
                recipient_list=[visitor.email], fail_silently=True,
            )
            n.status = "sent"
            n.sent_at = timezone.now()
            n.save(update_fields=["status", "sent_at"])
            sent += 1
        except Exception:
            n.status = "failed"
            n.save(update_fields=["status"])

    if new_status == "checked_in" and host:
        for u in _resolve_recipients(site=site):
            try:
                Notification.objects.create(
                    tenant_id=visit_request.tenant_id,
                    recipient=u, channel="in_app",
                    subject=f"Visiteur arrivé : {visitor}",
                    body=(f"{visitor.first_name} {visitor.last_name} vient d'arriver "
                          f"sur {site.name if site else '—'} pour son rendez-vous "
                          f"avec {host.first_name} {host.last_name}."),
                    payload={"visit_request_id": visit_request.id},
                    status="queued",
                )
                sent += 1
            except Exception:
                logger.exception("notify_visit_status_change failed for user=%s", u.id)
    return sent


def notify_export_ready(export_request) -> int:
    """Notifie le demandeur RGPD que son ZIP est prêt."""
    if not export_request.requested_by or not export_request.requested_by.email:
        return 0
    try:
        from notifications.models import Notification
        n = Notification.objects.create(
            tenant_id=export_request.tenant_id,
            recipient=export_request.requested_by, channel="email",
            subject="[KAYDAN SHIELD] Votre export RGPD est prêt",
            body=(f"Votre export est disponible pendant 7 jours.\n"
                  f"Connectez-vous au back-office pour le télécharger.\n"
                  f"Référence : DataExportRequest #{export_request.id}"),
            payload={"export_id": export_request.id},
            status="queued",
        )
        ok = _send_email_transactional(n)
        return 1 if ok else 0
    except Exception:
        logger.exception("notify_export_ready failed")
        return 0


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
