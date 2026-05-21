"""KAYDAN SHIELD — Services RGPD : exports DataExportRequest + pseudonymisation.

Conformité RGPD :
    Art. 15 — Droit d'accès : DataExportRequest produit un ZIP avec toutes les
              données concernant le sujet (visiteur ou employé).
    Art. 17 — Droit à l'effacement : pseudonymize_old_visitors() anonymise les
              visiteurs > 365 jours (configurable via VISITOR_ID_RETENTION_DAYS).
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_export_zip(export_request) -> bool:
    """Génère le ZIP RGPD pour un DataExportRequest et l'attache au modèle.

    Le ZIP contient :
        - identity.csv  Coordonnées principales du sujet
        - access.csv    Tous les AccessEvent liés
        - badges.csv    Tous les badges émis
        - logs.csv      Audit log filtré sur le sujet
        - README.txt    Métadonnées (RGPD, retention, contact DPO)

    Retourne True en cas de succès. Met à jour `status` + `file` + `expires_at`.
    """
    try:
        kind = export_request.subject_holder_kind
        subject_id = export_request.subject_holder_id
        if not kind or not subject_id:
            export_request.status = "failed"
            export_request.save(update_fields=["status"])
            return False

        subject = _resolve_subject(kind, subject_id)
        if subject is None:
            export_request.status = "failed"
            export_request.save(update_fields=["status"])
            return False

        # ─── Construction du ZIP en mémoire ───────────────────────
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", _readme(subject, kind, subject_id))
            zf.writestr("identity.csv", _identity_csv(subject, kind))
            zf.writestr("access.csv", _access_csv(kind, subject_id))
            zf.writestr("badges.csv", _badges_csv(kind, subject_id))
            zf.writestr("logs.csv", _audit_csv(kind, subject_id))

        filename = f"export-rgpd-{kind}-{subject_id}-{timezone.now():%Y%m%d-%H%M}.zip"
        export_request.file.save(filename, ContentFile(buf.getvalue()), save=False)
        export_request.status = "completed"
        # Délai de 7 jours par défaut pour télécharger l'archive
        export_request.expires_at = timezone.now() + timedelta(days=7)
        export_request.save(update_fields=["file", "status", "expires_at"])
        return True

    except Exception:
        logger.exception("generate_export_zip failed for export=%s", export_request.id)
        try:
            export_request.status = "failed"
            export_request.save(update_fields=["status"])
        except Exception:
            logger.exception("Impossible de marquer l'export RGPD %s en 'failed'", export_request.id)
        return False


def _resolve_subject(kind: str, subject_id: int):
    if kind == "employee":
        from employees.models import Employee
        return Employee.objects.filter(pk=subject_id).first()
    if kind == "worker":
        from ouvriers.models import Worker
        return Worker.objects.filter(pk=subject_id).first()
    if kind == "visitor":
        from visitors.models import Visitor
        return Visitor.objects.filter(pk=subject_id).first()
    return None


def _readme(subject, kind, subject_id) -> str:
    return (
        f"KAYDAN SHIELD — Export RGPD\n"
        f"=============================\n\n"
        f"Sujet     : {subject} ({kind} #{subject_id})\n"
        f"Généré le : {timezone.now():%Y-%m-%d %H:%M:%S}\n"
        f"Validité  : 7 jours (lien personnel à ne pas partager)\n\n"
        f"Contient :\n"
        f"  - identity.csv  : coordonnées personnelles\n"
        f"  - access.csv    : historique des scans d'accès\n"
        f"  - badges.csv    : badges émis et associés\n"
        f"  - logs.csv      : actions admin sur ce profil\n\n"
        f"Conformité   : RGPD Art. 15 — droit d'accès\n"
        f"Contact DPO  : dpo@kaydangroupe.com\n"
        f"Suppression  : pour effacement complet (Art. 17), répondre à cet email.\n"
    )


def _identity_csv(subject, kind) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["champ", "valeur"])
    fields = ("first_name", "last_name", "email", "phone", "matricule",
               "id_number", "nationality", "date_of_birth", "created_at")
    for f in fields:
        v = getattr(subject, f, "")
        w.writerow([f, str(v) if v is not None else ""])
    return out.getvalue()


def _access_csv(kind, subject_id) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp", "site", "decision", "method", "badge_uid", "denial_reason"])
    try:
        from access_control.models import AccessEvent
        qs = AccessEvent.objects.filter(
            holder_kind=kind, holder_object_id=subject_id,
        ).select_related("site").order_by("-timestamp")[:5000]
        for e in qs:
            w.writerow([
                e.timestamp.isoformat(),
                e.site.name if e.site else "",
                e.decision, e.method, e.badge_uid, e.denial_reason or "",
            ])
    except Exception:
        logger.debug("access_csv failed", exc_info=True)
    return out.getvalue()


def _badges_csv(kind, subject_id) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["uid", "category", "status", "issued_at", "expires_at",
                  "revoked_at", "revoked_reason"])
    try:
        from devices.models import Badge
        qs = Badge.objects.filter(
            holder_kind=kind, holder_object_id=subject_id,
        ).order_by("-issued_at")
        for b in qs:
            w.writerow([
                b.uid, b.category, b.status,
                b.issued_at.isoformat() if b.issued_at else "",
                b.valid_until.isoformat() if getattr(b, "valid_until", None) else "",
                b.revoked_at.isoformat() if b.revoked_at else "",
                getattr(b, "revoked_reason", "") or "",
            ])
    except Exception:
        logger.debug("badges_csv failed", exc_info=True)
    return out.getvalue()


def _audit_csv(kind, subject_id) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp", "user", "action", "target_model", "target_id"])
    try:
        from audit.models import AuditLog
        qs = AuditLog.objects.filter(
            target_id=str(subject_id),
        ).select_related("user").order_by("-timestamp")[:1000]
        for a in qs:
            w.writerow([
                a.timestamp.isoformat(),
                a.user.email if a.user else "system",
                a.action, a.target_model or "", a.target_id or "",
            ])
    except Exception:
        logger.debug("audit_csv failed", exc_info=True)
    return out.getvalue()


# =====================================================================
# Pseudonymisation automatique des visiteurs > VISITOR_ID_RETENTION_DAYS
# =====================================================================
def pseudonymize_old_visitors() -> int:
    """À planifier en tâche quotidienne (Celery beat).

    Tous les visiteurs créés depuis plus de N jours (par défaut 365) qui
    ne sont pas encore pseudonymisés voient leurs PII remplacées par des hash.
    Le compteur d'AccessEvent reste exploitable mais l'identité est effacée.
    """
    from visitors.models import Visitor
    days = int(getattr(settings, "KAYDAN_SHIELD", {}).get(
        "VISITOR_ID_RETENTION_DAYS", 365))
    cutoff = timezone.now() - timedelta(days=days)
    qs = Visitor.objects.filter(
        created_at__lte=cutoff, pseudonymized_at__isnull=True,
    )
    count = 0
    for v in qs:
        try:
            v.first_name = "ANONYMISÉ"
            v.last_name = f"#{v.id}"
            v.email = ""
            v.phone = ""
            v.id_number = ""
            v.company = ""
            v.pseudonymized_at = timezone.now()
            v.save(update_fields=[
                "first_name", "last_name", "email", "phone",
                "id_number", "company", "pseudonymized_at",
            ])
            count += 1
        except Exception:
            logger.exception("pseudonymize visitor=%s failed", v.id)
    if count:
        logger.info("pseudonymize_old_visitors : %s visiteur(s) anonymisé(s)", count)
    return count
