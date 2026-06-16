"""Tasks Celery — dispatch des notifications en file vers email/SMS/Webhook.

Lance toutes les 60s via beat. Consomme ``Notification.objects.filter(
status='queued')`` et tente la délivrance via le canal approprié.

Idempotent : passe le status à 'sent' / 'failed' après tentative.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="notifications.dispatch_queued",
             autoretry_for=(Exception,),
             retry_kwargs={"max_retries": 1, "countdown": 60})
def dispatch_queued(batch_size: int = 100) -> dict:
    """Dispatche jusqu'à `batch_size` notifications en file.

    Returns:
        {"sent": N, "failed": M, "skipped": K}
    """
    from .models import Notification

    qs = (Notification.objects
          .filter(status="queued")
          .select_related("recipient", "tenant")
          .order_by("created_at")[:batch_size])

    sent = 0; failed = 0; skipped = 0

    for notif in qs:
        try:
            if notif.channel == "email":
                if not _send_email(notif):
                    skipped += 1
                    continue
            elif notif.channel == "sms":
                if not _send_sms(notif):
                    skipped += 1
                    continue
            elif notif.channel == "webhook":
                if not _send_webhook(notif):
                    skipped += 1
                    continue
            elif notif.channel == "websocket":
                # Pas d'envoi sortant — c'est consommé par la subscription WS
                notif.status = "sent"
                notif.sent_at = timezone.now()
                notif.save(update_fields=["status", "sent_at"])
                sent += 1
                continue
            else:
                logger.warning("Canal de notification inconnu : %s", notif.channel)
                skipped += 1
                continue

            notif.status = "sent"
            notif.sent_at = timezone.now()
            notif.save(update_fields=["status", "sent_at"])
            sent += 1
        except Exception as exc:
            logger.exception("dispatch notif %s failed", notif.pk)
            notif.status = "failed"
            notif.failure_reason = str(exc)[:500]
            notif.save(update_fields=["status", "failure_reason"])
            failed += 1

    return {"sent": sent, "failed": failed, "skipped": skipped,
            "batch_size": batch_size}


def _send_email(notif) -> bool:
    """Envoie l'email via Django EmailMessage. Returns True si envoyé."""
    recipient_email = None
    if notif.recipient:
        recipient_email = notif.recipient.email
    elif notif.payload.get("to_email"):
        recipient_email = notif.payload["to_email"]

    if not recipient_email:
        logger.warning("Notif %s : pas de destinataire email", notif.pk)
        notif.status = "failed"
        notif.failure_reason = "Pas de destinataire email"
        notif.save(update_fields=["status", "failure_reason"])
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL",
                          "no-reply@kaydangroupe.com")
    msg = EmailMessage(
        subject=notif.subject or "Notification KAYDAN SHIELD",
        body=notif.body,
        from_email=from_email,
        to=[recipient_email],
    )
    msg.send(fail_silently=False)
    return True


def _send_sms(notif) -> bool:
    """Envoie via le backend SMS configuré (console / twilio / africastalking)."""
    backend = getattr(settings, "KAYDAN_SHIELD", {}).get("SMS", {}).get(
        "backend", "console",
    )

    to_phone = notif.payload.get("to_phone")
    if not to_phone and notif.recipient:
        to_phone = getattr(notif.recipient, "phone", None)
    if not to_phone:
        logger.warning("Notif %s : pas de destinataire SMS", notif.pk)
        return False

    if backend == "console":
        logger.info("[SMS console] to=%s body=%s", to_phone, notif.body[:140])
        return True
    if backend == "africastalking":
        try:
            import africastalking
            africastalking.initialize(
                username=settings.AFRICAS_TALKING_USERNAME,
                api_key=settings.AFRICAS_TALKING_API_KEY,
            )
            africastalking.SMS.send(
                notif.body, [to_phone],
                sender_id=getattr(settings, "KAYDAN_SHIELD", {}).get(
                    "SMS", {}).get("from", "KAYDAN"),
            )
            return True
        except Exception as exc:
            logger.exception("Africastalking failed")
            raise
    if backend == "twilio":
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID,
                              settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=notif.body, to=to_phone,
                from_=settings.TWILIO_FROM,
            )
            return True
        except Exception:
            logger.exception("Twilio failed")
            raise
    return False


def _send_webhook(notif) -> bool:
    """POSTs notif.body en JSON à l'URL configurée dans payload['webhook_url']."""
    import json

    import requests
    url = notif.payload.get("webhook_url")
    if not url:
        return False
    payload = {
        "subject": notif.subject,
        "body": notif.body,
        "tenant": str(notif.tenant_id),
        "data": notif.payload,
    }
    r = requests.post(url, json=payload, timeout=10)
    notif.provider_response = {
        "status_code": r.status_code, "body": r.text[:500],
    }
    r.raise_for_status()
    return True
