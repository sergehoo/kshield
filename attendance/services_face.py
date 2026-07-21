"""KAYDAN SHIELD — Service confirmation présence par reconnaissance faciale.

**Principe clé** : le pointage RFID reste la source de vérité. Ce service
**enrichit** uniquement, il ne crée jamais de Punch lui-même. Il :

1. Reçoit un FaceSightingEvent (déjà persisté par le camera worker).
2. Détermine si c'est une arrivée (avant ~14h) ou un départ (après 14h).
3. Cherche un Punch RFID correspondant ±4h sur la même date.
4. Crée 1 FaceCheckinConfirmation (unique par employee/date/kind) avec :
   - status='confirmed' si badge + face trouvés
   - status='face_only' si visage sans badge → FraudAlert ouverte
5. Tout est idempotent : un 2e sighting le même jour/kind ne crée pas de doublon.

**Ne touche jamais le pointage RFID existant** :
- Pas de création de Punch
- Pas de modification de Punch.status
- Pas d'écriture sur AttendanceDay

Les seules tables touchées sont :
- attendance.FaceCheckinConfirmation (création/lecture)
- antifraud.FraudAlert (création optionnelle si suspect)
"""
from __future__ import annotations

import logging
from datetime import datetime, time as time_cls, timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration métier
# ---------------------------------------------------------------------------
def _cfg():
    """Récupère la conf face presence depuis settings (avec defaults)."""
    base = settings.KAYDAN_SHIELD.get("FACE_PRESENCE", {})
    return {
        # Heure cut-off arrivée/départ (local time). Avant = arrival, après = departure.
        "ARRIVAL_DEPARTURE_CUTOFF_HOUR": base.get("ARRIVAL_DEPARTURE_CUTOFF_HOUR", 14),
        # Fenêtre de matching face↔badge (en heures, de part et d'autre).
        "MATCH_WINDOW_HOURS": base.get("MATCH_WINDOW_HOURS", 4),
        # Si True, ouvre une FraudAlert sur visage sans badge.
        "ALERT_ON_FACE_WITHOUT_BADGE": base.get("ALERT_ON_FACE_WITHOUT_BADGE", True),
        # Sévérité de l'alerte (low/medium/high/critical).
        "ALERT_SEVERITY": base.get("ALERT_SEVERITY", "medium"),
    }


def _is_arrival(local_ts) -> bool:
    """Avant l'heure cut-off (par défaut 14h) → arrivée, sinon départ."""
    return local_ts.hour < _cfg()["ARRIVAL_DEPARTURE_CUTOFF_HOUR"]


# ---------------------------------------------------------------------------
# Recherche du punch RFID correspondant
# ---------------------------------------------------------------------------
def _find_matching_punch(employee, sighting_ts, kind: str):
    """Cherche un Punch RFID dans la fenêtre temporelle.

    Args:
        employee: instance Employee
        sighting_ts: datetime aware (UTC ou tz-aware)
        kind: "arrival" | "departure"

    Retourne le Punch le plus proche (par delta absolu), ou None.
    """
    from attendance.models import Punch
    from django.contrib.contenttypes.models import ContentType
    from employees.models import Employee

    window_h = _cfg()["MATCH_WINDOW_HOURS"]
    ct = ContentType.objects.get_for_model(Employee)

    # Mapping kind face → types de Punch RFID acceptés
    # Le modèle Punch utilise 4 types : morning_in, morning_out, evening_in, evening_out.
    # Pour arrival on accepte (morning_in, evening_in) — pour départ : (morning_out, evening_out).
    if kind == "arrival":
        acceptable_types = ("morning_in", "evening_in")
    else:
        acceptable_types = ("morning_out", "evening_out")

    qs = Punch.objects.filter(
        holder_content_type=ct,
        holder_object_id=employee.pk,
        type__in=acceptable_types,
        timestamp__gte=sighting_ts - timedelta(hours=window_h),
        timestamp__lte=sighting_ts + timedelta(hours=window_h),
    ).order_by("timestamp")

    if not qs.exists():
        return None
    # Sélectionne celui dont le delta absolu est minimal
    best = None
    best_abs_delta = None
    for p in qs:
        delta = abs((p.timestamp - sighting_ts).total_seconds())
        if best_abs_delta is None or delta < best_abs_delta:
            best, best_abs_delta = p, delta
    return best


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------
def confirm_attendance_from_sighting(sighting):
    """Crée/met à jour une FaceCheckinConfirmation à partir d'un sighting matché.

    **Idempotent** : appel multiple pour le même (employee, date, kind) → renvoie
    la confirmation existante sans rien recréer. Le 1er sighting du jour gagne.

    Returns:
        FaceCheckinConfirmation | None (None si sighting non matché).
    """
    if not sighting or not sighting.matched or not sighting.employee_id:
        return None

    from attendance.models import FaceCheckinConfirmation

    local_ts = timezone.localtime(sighting.timestamp)
    date = local_ts.date()
    kind = "arrival" if _is_arrival(local_ts) else "departure"

    # Idempotence : si on a déjà une confirmation pour cet employé/date/kind, on
    # NE remplace PAS. Le 1er sighting de la journée fait foi.
    existing = FaceCheckinConfirmation.objects.filter(
        employee_id=sighting.employee_id, date=date, kind=kind,
    ).first()
    if existing:
        return existing

    # Cherche le punch RFID associé
    punch = _find_matching_punch(sighting.employee, sighting.timestamp, kind)
    if punch:
        delta = int((punch.timestamp - sighting.timestamp).total_seconds())
        status = "confirmed"
    else:
        delta = None
        status = "face_only"

    confirmation = FaceCheckinConfirmation.objects.create(
        employee_id=sighting.employee_id,
        date=date,
        kind=kind,
        sighting=sighting,
        punch=punch,
        delta_seconds=delta,
        status=status,
    )

    # Alerte anti-fraude si visage sans badge (potentiellement quelqu'un qui
    # est entré dans les locaux sans badger)
    if status == "face_only" and _cfg()["ALERT_ON_FACE_WITHOUT_BADGE"]:
        _open_fraud_alert(sighting, kind, confirmation)

    return confirmation


def reconcile_badge_only_today():
    """Job de fin de journée : marque les Punches RFID sans face comme 'badge_only'.

    À planifier en Celery beat tous les soirs (ex. 21h, après l'heure de départ
    max). Identifie les employés qui ont badgé mais qu'aucune caméra n'a vus.
    Utile pour anti-fraude : badge prêté à un collègue ?
    """
    from attendance.models import FaceCheckinConfirmation, Punch
    from django.contrib.contenttypes.models import ContentType
    from employees.models import Employee

    today = timezone.localdate()
    ct = ContentType.objects.get_for_model(Employee)

    # Tous les Punches d'employés aujourd'hui
    punches = Punch.objects.filter(
        holder_content_type=ct,
        timestamp__date=today,
    ).select_related()

    # Employés couverts par une FaceCheckinConfirmation (peu importe le status)
    covered = set(FaceCheckinConfirmation.objects.filter(
        date=today,
    ).values_list("employee_id", "kind"))

    created = 0
    for p in punches:
        emp_id = p.holder_object_id
        if not emp_id:
            continue
        kind = "arrival" if p.type in ("morning_in", "evening_in") else "departure"
        if (emp_id, kind) in covered:
            continue
        # Pas de confirmation face → créer une entrée badge_only
        FaceCheckinConfirmation.objects.update_or_create(
            employee_id=emp_id, date=today, kind=kind,
            defaults={
                "punch": p, "sighting": None,
                "status": "badge_only",
                "notes": "Auto-créé par reconcile (badge sans confirmation visage)",
            },
        )
        created += 1
    return created


# ---------------------------------------------------------------------------
# Création FraudAlert sur visage sans badge
# ---------------------------------------------------------------------------
def _open_fraud_alert(sighting, kind: str, confirmation):
    """Ouvre une FraudAlert "FACE_NO_BADGE" pour la sécurité."""
    try:
        from antifraud.models import FraudAlert, FraudRule
    except ImportError:
        logger.debug("antifraud pas dispo, skip alerte.")
        return

    rule_code = "FACE_NO_BADGE"
    severity = _cfg()["ALERT_SEVERITY"]
    emp = sighting.employee
    tenant = emp.tenant
    rule, _ = FraudRule.objects.get_or_create(
        tenant=tenant,
        code=rule_code,
        defaults={
            "name": "Visage détecté sans badge",
            "severity": severity,
            "description": "Un employé reconnu n'a pas de pointage badge correspondant.",
        },
    )
    message = (
        f"Visage de {emp.first_name} {emp.last_name} "
        f"({emp.matricule}) détecté à "
        f"{timezone.localtime(sighting.timestamp).strftime('%H:%M')} "
        f"sans badge correspondant ({kind})."
    )
    try:
        FraudAlert.objects.create(
            tenant=tenant,
            rule=rule,
            site=sighting.site,
            severity=severity,
            status="open",
            primary_holder_kind="employee",
            primary_holder_id=emp.pk,
            evidence={
                "rule_code": rule_code,
                "sighting_id": sighting.pk,
                "confirmation_id": confirmation.pk,
                "employee_id": emp.pk,
                "kind": kind,
                "camera_id": sighting.camera_id,
                "message": message,
            },
            raised_at=timezone.now(),
        )
    except Exception:
        logger.exception("Création FraudAlert FACE_NO_BADGE échouée")
