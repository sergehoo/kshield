"""KAYDAN SHIELD — Service SMS abstract.

Backends supportés (lazy) :
    console   → log dans stdout (dev)
    twilio    → API Twilio (production internationale)
    africastalking → API Africa's Talking (CI / Afrique de l'Ouest)

Configuration dans `settings.KAYDAN_SHIELD["SMS"]` :
    {
      "backend": "console" | "twilio" | "africastalking",
      "from": "+225...",
      "twilio": {"account_sid": "...", "auth_token": "..."},
      "africastalking": {"username": "...", "api_key": "...", "sender_id": "..."},
    }
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def send_sms(to: str, body: str) -> bool:
    """Envoie un SMS via le backend configuré.

    Le numéro `to` doit être au format E.164 (+225XXXXXXXX).
    Retourne True si l'envoi a été déclenché côté provider.
    """
    if not to or not body:
        return False
    cfg = getattr(settings, "KAYDAN_SHIELD", {}).get("SMS", {})
    backend = cfg.get("backend", "console")
    sender = cfg.get("from", "KAYDAN")

    try:
        if backend == "twilio":
            return _send_twilio(to, body, cfg.get("twilio", {}), sender)
        if backend == "africastalking":
            return _send_africastalking(to, body, cfg.get("africastalking", {}))
        return _send_console(to, body, sender)
    except Exception:
        logger.exception("SMS send failed (backend=%s)", backend)
        return False


def _send_console(to: str, body: str, sender: str) -> bool:
    logger.info("[SMS console] from=%s to=%s body=%s", sender, to, body[:140])
    return True


def _send_twilio(to: str, body: str, opts: dict, sender: str) -> bool:
    sid = opts.get("account_sid")
    token = opts.get("auth_token")
    if not (sid and token):
        logger.warning("Twilio config incomplète — fallback console")
        return _send_console(to, body, sender)
    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning("twilio non installé — pip install twilio")
        return _send_console(to, body, sender)
    Client(sid, token).messages.create(to=to, from_=sender, body=body)
    return True


def _send_africastalking(to: str, body: str, opts: dict) -> bool:
    username = opts.get("username")
    api_key = opts.get("api_key")
    sender_id = opts.get("sender_id", "KAYDAN")
    if not (username and api_key):
        logger.warning("Africastalking config incomplète — fallback console")
        return _send_console(to, body, sender_id)
    try:
        import africastalking
    except ImportError:
        logger.warning("africastalking non installé — pip install africastalking")
        return _send_console(to, body, sender_id)
    africastalking.initialize(username, api_key)
    africastalking.SMS.send(body, [to], sender_id=sender_id)
    return True


# ─── Helpers métier ─────────────────────────────────────────────────────
def send_visit_qr_sms(visit_request) -> bool:
    """Envoie au visiteur le lien/code QR de sa visite par SMS."""
    visitor = visit_request.visitor
    if not visitor or not visitor.phone:
        return False
    site = visit_request.site.name if visit_request.site else "KAYDAN"
    body = (
        f"KAYDAN SHIELD — Bonjour {visitor.first_name}, "
        f"votre visite sur {site} est confirmée. "
        f"Présentez-vous à l'accueil avec votre pièce d'identité. "
        f"Réf: VR{visit_request.id}"
    )
    return send_sms(visitor.phone, body)


def send_alert_sms(phone: str, alert_message: str) -> bool:
    return send_sms(phone, f"KAYDAN ALERTE: {alert_message[:140]}")
