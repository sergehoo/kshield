"""KAYDAN SHIELD — Signals Django qui émettent des webhooks sortants.

Branchés au moment de l'app `core` ready(). Best-effort : si la config
WEBHOOKS est vide, ces handlers ne font rien. Si un webhook échoue, il est
loggué mais ne bloque PAS la transaction principale.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _safe(callback, *args, **kwargs):
    try:
        callback(*args, **kwargs)
    except Exception:
        logger.exception("Webhook signal handler failed")


@receiver(post_save, sender="employees.Employee")
def _employee_saved(sender, instance, created, **kwargs):
    from core.webhooks import emit_employee_event
    event = "employee.created" if created else "employee.updated"
    _safe(emit_employee_event, instance, event=event)


@receiver(post_save, sender="ouvriers.Worker")
def _worker_saved(sender, instance, created, **kwargs):
    from core.webhooks import emit_worker_event
    event = "worker.created" if created else "worker.updated"
    _safe(emit_worker_event, instance, event=event)


@receiver(post_save, sender="antifraud.FraudAlert")
def _fraud_alert_saved(sender, instance, created, **kwargs):
    if not created:
        return
    from core.webhooks import emit_fraud_alert_event
    _safe(emit_fraud_alert_event, instance)
