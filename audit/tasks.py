"""KAYDAN SHIELD — Tâches Celery RGPD.

À planifier dans django-celery-beat :
    audit.pseudonymize_visitors_daily   → tous les jours à 02:00
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="audit.pseudonymize_visitors_daily")
def pseudonymize_visitors_daily() -> dict:
    """Anonymise les visiteurs > VISITOR_ID_RETENTION_DAYS."""
    try:
        from audit.services import pseudonymize_old_visitors
        n = pseudonymize_old_visitors()
        return {"pseudonymized": n}
    except Exception:
        logger.exception("pseudonymize_visitors_daily failed")
        return {"pseudonymized": 0, "error": True}


@shared_task(name="audit.generate_export_zip_async")
def generate_export_zip_async(export_request_id: int) -> dict:
    """Génère un ZIP RGPD pour un DataExportRequest."""
    from audit.models import DataExportRequest
    from audit.services import generate_export_zip
    try:
        req = DataExportRequest.objects.get(pk=export_request_id)
    except DataExportRequest.DoesNotExist:
        return {"export_id": export_request_id, "status": "missing"}
    ok = generate_export_zip(req)
    return {"export_id": export_request_id, "status": "completed" if ok else "failed"}
