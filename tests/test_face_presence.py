"""KAYDAN SHIELD — Tests du service face → presence confirmation.

Couverture :
  1. Sighting matché + Punch RFID trouvé dans la fenêtre → status=confirmed
  2. Sighting matché + AUCUN Punch → status=face_only + FraudAlert ouverte
  3. Sighting non matché (employee=None) → no-op
  4. Idempotence : 2e sighting le même jour/kind n'écrase pas le 1er
  5. Reconcile fin de journée : Punch sans face → status=badge_only
  6. Cutoff arrival/departure (avant 14h vs après 14h)
"""
from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


@pytest.fixture
def base_setup(db):
    """Tenant + filiale + site + employé + caméra."""
    from core.models import Company, Tenant
    from devices.models import Camera
    from employees.models import Employee
    from sites.models import Site

    tenant = Tenant.objects.first() or Tenant.objects.create(
        name="KAYDAN", code="KAYDAN",
    )
    company = Company.objects.create(tenant=tenant, name="BTP", code="BTP",
                                        sector="construction")
    site = Site.objects.create(tenant=tenant, company=company,
                                  name="Siège", code="HQ",
                                  type="office", status="active")
    employee = Employee.objects.create(
        tenant=tenant, company=company, matricule="EMP001",
        first_name="Alice", last_name="Diallo", email="alice@kaydan.test",
    )
    camera = Camera.objects.create(
        site=site, name="Cam Entrée", rtsp_url="rtsp://dummy",
        is_active=True,
    )
    return tenant, company, site, employee, camera


def _make_sighting(camera, site, employee, ts=None, matched=True):
    """Crée un FaceSightingEvent à un instant donné."""
    from attendance.models import FaceSightingEvent
    return FaceSightingEvent.objects.create(
        camera=camera, site=site, employee=employee if matched else None,
        timestamp=ts or timezone.now(),
        face_score=0.85, matched=matched, bbox=[10, 10, 100, 100],
    )


def _make_punch(employee, ts, ptype="morning_in", site=None):
    """Crée un Punch RFID employé."""
    from attendance.models import Punch
    ct = ContentType.objects.get_for_model(employee)
    return Punch.objects.create(
        tenant=employee.tenant, site=site or employee.company.sites.first(),
        holder_kind="employee", holder_content_type=ct, holder_object_id=employee.pk,
        type=ptype, timestamp=ts,
    )


# ---------------------------------------------------------------------------
# 1. Sighting + Punch dans la fenêtre → confirmed
# ---------------------------------------------------------------------------
def test_sighting_with_matching_punch_confirms(base_setup):
    from attendance.models import FaceCheckinConfirmation
    from attendance.services_face import confirm_attendance_from_sighting

    tenant, company, site, emp, cam = base_setup
    # 8h00 = arrivée
    arrival_ts = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    _make_punch(emp, arrival_ts + timedelta(minutes=2), "morning_in", site)
    sighting = _make_sighting(cam, site, emp, ts=arrival_ts)

    conf = confirm_attendance_from_sighting(sighting)
    assert conf is not None
    assert conf.status == "confirmed"
    assert conf.kind == "arrival"
    assert conf.punch is not None
    assert conf.employee_id == emp.pk
    assert abs(conf.delta_seconds) == 120  # 2 minutes


# ---------------------------------------------------------------------------
# 2. Sighting matché mais AUCUN Punch → face_only + FraudAlert
# ---------------------------------------------------------------------------
def test_sighting_without_punch_creates_alert(base_setup):
    from antifraud.models import FraudAlert
    from attendance.services_face import confirm_attendance_from_sighting

    tenant, company, site, emp, cam = base_setup
    sighting = _make_sighting(cam, site, emp,
                                 ts=timezone.now().replace(hour=9, minute=0))
    # AUCUN punch créé

    conf = confirm_attendance_from_sighting(sighting)
    assert conf is not None
    assert conf.status == "face_only"
    assert conf.punch is None
    assert conf.delta_seconds is None

    # Une FraudAlert a été ouverte
    alerts = FraudAlert.objects.filter(evidence__rule_code="FACE_NO_BADGE")
    assert alerts.count() == 1
    alert = alerts.first()
    assert alert.evidence["employee_id"] == emp.pk
    assert alert.evidence["kind"] == "arrival"


# ---------------------------------------------------------------------------
# 3. Sighting non matché (employee=None) → no-op
# ---------------------------------------------------------------------------
def test_unmatched_sighting_skipped(base_setup):
    from attendance.models import FaceCheckinConfirmation
    from attendance.services_face import confirm_attendance_from_sighting

    tenant, company, site, emp, cam = base_setup
    sighting = _make_sighting(cam, site, None, matched=False)

    conf = confirm_attendance_from_sighting(sighting)
    assert conf is None
    assert FaceCheckinConfirmation.objects.count() == 0


# ---------------------------------------------------------------------------
# 4. Idempotence : 2e sighting le même jour/kind ne crée pas de doublon
# ---------------------------------------------------------------------------
def test_second_sighting_same_kind_is_idempotent(base_setup):
    from attendance.models import FaceCheckinConfirmation
    from attendance.services_face import confirm_attendance_from_sighting

    tenant, company, site, emp, cam = base_setup
    arrival_ts = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    _make_punch(emp, arrival_ts, "morning_in", site)

    s1 = _make_sighting(cam, site, emp, ts=arrival_ts)
    s2 = _make_sighting(cam, site, emp, ts=arrival_ts + timedelta(minutes=10))

    conf1 = confirm_attendance_from_sighting(s1)
    conf2 = confirm_attendance_from_sighting(s2)

    # 1er crée, 2e renvoie la MÊME confirmation (pas de doublon)
    assert conf1.pk == conf2.pk
    assert FaceCheckinConfirmation.objects.filter(
        employee=emp, date=arrival_ts.date(), kind="arrival",
    ).count() == 1


# ---------------------------------------------------------------------------
# 5. Cutoff arrival/departure
# ---------------------------------------------------------------------------
def test_morning_sighting_classified_as_arrival(base_setup):
    from attendance.services_face import confirm_attendance_from_sighting

    _, _, site, emp, cam = base_setup
    morning_ts = timezone.now().replace(hour=8, minute=30)
    sighting = _make_sighting(cam, site, emp, ts=morning_ts)
    conf = confirm_attendance_from_sighting(sighting)
    assert conf.kind == "arrival"


def test_evening_sighting_classified_as_departure(base_setup):
    from attendance.services_face import confirm_attendance_from_sighting

    _, _, site, emp, cam = base_setup
    evening_ts = timezone.now().replace(hour=18, minute=15)
    sighting = _make_sighting(cam, site, emp, ts=evening_ts)
    conf = confirm_attendance_from_sighting(sighting)
    assert conf.kind == "departure"


# ---------------------------------------------------------------------------
# 6. Reconcile : badge sans face
# ---------------------------------------------------------------------------
def test_reconcile_creates_badge_only_for_unseen_punch(base_setup):
    from attendance.models import FaceCheckinConfirmation
    from attendance.services_face import reconcile_badge_only_today

    _, _, site, emp, cam = base_setup
    today_ts = timezone.now().replace(hour=8, minute=0)
    _make_punch(emp, today_ts, "morning_in", site)
    # AUCUN sighting créé

    created = reconcile_badge_only_today()
    assert created == 1

    conf = FaceCheckinConfirmation.objects.get(employee=emp, kind="arrival")
    assert conf.status == "badge_only"
    assert conf.sighting is None
    assert conf.punch is not None


def test_reconcile_skips_already_confirmed(base_setup):
    """Un employé déjà vu par une caméra ne re-crée pas une badge_only."""
    from attendance.models import FaceCheckinConfirmation
    from attendance.services_face import (confirm_attendance_from_sighting,
                                              reconcile_badge_only_today)

    _, _, site, emp, cam = base_setup
    arrival_ts = timezone.now().replace(hour=8, minute=0)
    _make_punch(emp, arrival_ts, "morning_in", site)
    sighting = _make_sighting(cam, site, emp, ts=arrival_ts)
    confirm_attendance_from_sighting(sighting)

    # Au reconcile, on a déjà une confirmation → pas de nouvelle creation
    created = reconcile_badge_only_today()
    assert created == 0
    assert FaceCheckinConfirmation.objects.filter(employee=emp).count() == 1
