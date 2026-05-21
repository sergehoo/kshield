"""KAYDAN SHIELD — Tâches Celery du module reports.

Inclut :
    · generate_weekly_digest — chaque lundi 07h00 (Africa/Abidjan)
    · generate_monthly_digest — chaque 1er du mois 07h30
    · generate_digest_for_tenant — variante on-demand (admin trigger)

Planifier dans Celery Beat (DatabaseScheduler conseillé). Exemple inline :

    CELERY_BEAT_SCHEDULE = {
        "weekly_executive_digest": {
            "task": "reports.generate_weekly_digest",
            "schedule": crontab(hour=7, minute=0, day_of_week="monday"),
        },
        "monthly_executive_digest": {
            "task": "reports.generate_monthly_digest",
            "schedule": crontab(hour=7, minute=30, day_of_month="1"),
        },
    }
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _iter_tenants():
    """Itère sur tous les tenants actifs (multi-tenant safe)."""
    from core.models import Tenant
    return Tenant.objects.filter(is_active=True)


@shared_task(name="reports.generate_weekly_digest", bind=True,
              max_retries=2, default_retry_delay=300)
def generate_weekly_digest(self, send_email: bool = True) -> dict:
    """Génère et envoie le digest hebdomadaire pour chaque tenant actif."""
    from reports.services_digest import run_digest_pipeline
    results = []
    for tenant in _iter_tenants():
        try:
            r = run_digest_pipeline(tenant, period="weekly",
                                      send_email=send_email)
            results.append({"tenant_id": tenant.id, **r})
        except Exception as exc:
            logger.exception(
                "generate_weekly_digest: tenant=%s a échoué", tenant.id)
            results.append({"tenant_id": tenant.id, "error": str(exc)[:200]})
    return {"period": "weekly", "results": results}


@shared_task(name="reports.generate_monthly_digest", bind=True,
              max_retries=2, default_retry_delay=300)
def generate_monthly_digest(self, send_email: bool = True) -> dict:
    """Génère et envoie le digest mensuel pour chaque tenant actif."""
    from reports.services_digest import run_digest_pipeline
    results = []
    for tenant in _iter_tenants():
        try:
            r = run_digest_pipeline(tenant, period="monthly",
                                      send_email=send_email)
            results.append({"tenant_id": tenant.id, **r})
        except Exception as exc:
            logger.exception(
                "generate_monthly_digest: tenant=%s a échoué", tenant.id)
            results.append({"tenant_id": tenant.id, "error": str(exc)[:200]})
    return {"period": "monthly", "results": results}


@shared_task(name="reports.generate_digest_for_tenant")
def generate_digest_for_tenant(tenant_id: int, period: str = "weekly",
                                 send_email: bool = False) -> dict:
    """On-demand : trigger admin manuel depuis l'UI (re-generate ou backfill)."""
    from core.models import Tenant
    from reports.services_digest import run_digest_pipeline
    try:
        tenant = Tenant.objects.get(pk=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return {"error": "tenant introuvable"}
    return run_digest_pipeline(tenant, period=period, send_email=send_email)


@shared_task(name="reports.regenerate_digest")
def regenerate_digest(digest_id: int, send_email: bool = False) -> dict:
    """Re-génère un digest existant (utile après ajustement de prompt/data)."""
    from reports.models import ExecutiveDigest
    from reports.services_digest import generate_digest, send_digest_email
    try:
        digest = ExecutiveDigest.objects.get(pk=digest_id)
    except ExecutiveDigest.DoesNotExist:
        return {"error": "digest introuvable"}
    ok = generate_digest(digest)
    sent = 0
    if ok and send_email:
        try:
            sent = send_digest_email(digest)
        except Exception:
            logger.exception("send_digest_email crash")
    return {
        "digest_id": digest.id,
        "status": digest.status,
        "sent_to": sent,
    }
