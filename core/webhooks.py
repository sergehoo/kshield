"""KAYDAN SHIELD — Service Webhooks sortants.

Permet à des systèmes tiers (HRIS, ERP, SIRH) d'être notifiés des événements
métier (Employee créé, Worker modifié, FraudAlert ouverte, etc.).

Configuration : `settings.KAYDAN_SHIELD["WEBHOOKS"]` =
    [{"event": "employee.created",
      "url": "https://hris.example.com/hooks/kaydan",
      "secret": "shared-secret-for-hmac"}]

Chaque payload est signé en HMAC-SHA256 avec le secret partagé. Header :
    X-KShield-Webhook-Signature: hex(hmac_sha256(secret, body))
    X-KShield-Webhook-Event: employee.created
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _matching_targets(event: str) -> list[dict]:
    cfg = getattr(settings, "KAYDAN_SHIELD", {}).get("WEBHOOKS", [])
    return [t for t in cfg if t.get("event") == event or t.get("event") == "*"]


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def dispatch(event: str, payload: dict[str, Any]) -> int:
    """Envoie le webhook à toutes les cibles configurées pour cet event.

    Retourne le nombre d'appels HTTP réussis (status < 400).
    """
    targets = _matching_targets(event)
    if not targets:
        return 0

    body_str = json.dumps(payload, default=str, ensure_ascii=False)
    body_bytes = body_str.encode("utf-8")

    success = 0
    try:
        import urllib.request
    except ImportError:
        return 0

    for t in targets:
        url = t.get("url")
        secret = t.get("secret", "")
        if not url:
            continue
        try:
            req = urllib.request.Request(
                url, data=body_bytes, method="POST",
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-KShield-Webhook-Event": event,
                    "X-KShield-Webhook-Signature": _sign(secret, body_bytes),
                    "User-Agent": "KAYDAN-SHIELD-Webhook/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status < 400:
                    success += 1
                    logger.info("Webhook %s → %s OK (HTTP %s)",
                                event, url, resp.status)
                else:
                    logger.warning("Webhook %s → %s HTTP %s", event, url, resp.status)
        except Exception as exc:
            logger.warning("Webhook %s → %s failed: %s", event, url, exc)
    return success


# ─── Helpers métier ───────────────────────────────────────────────────────
def emit_employee_event(employee, event: str = "employee.created") -> int:
    return dispatch(event, {
        "event": event,
        "employee": {
            "id": employee.id, "matricule": employee.matricule,
            "first_name": employee.first_name, "last_name": employee.last_name,
            "email": employee.email or None,
            "company": employee.company.code if employee.company_id else None,
            "status": employee.status,
        },
    })


def emit_worker_event(worker, event: str = "worker.created") -> int:
    return dispatch(event, {
        "event": event,
        "worker": {
            "id": worker.id, "matricule": worker.matricule,
            "first_name": worker.first_name, "last_name": worker.last_name,
            "trade": worker.trade.code if worker.trade_id else None,
            "subcontractor": worker.subcontractor.code if worker.subcontractor_id else None,
            "status": worker.status,
        },
    })


def emit_fraud_alert_event(alert, event: str = "fraud_alert.opened") -> int:
    return dispatch(event, {
        "event": event,
        "alert_id": alert.id,
        "rule_code": alert.rule.code if alert.rule_id else None,
        "severity": alert.severity,
        "site_id": alert.site_id,
        "primary_holder_kind": alert.primary_holder_kind,
        "primary_holder_id": alert.primary_holder_id,
        "raised_at": alert.raised_at.isoformat() if alert.raised_at else None,
    })
