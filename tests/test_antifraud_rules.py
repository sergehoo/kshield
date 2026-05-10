"""Tests des 4 règles anti-fraude implémentées dans antifraud.services."""
from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.fixture
def access_event(db, kaydan_tenant, site_chantier, employee):
    from access_control.models import AccessEvent
    return AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="B-RULE-001",
        decision="granted", method="nfc",
        holder_kind="employee", holder_object_id=employee.id,
    )


@pytest.mark.integration
def test_badge_loan_handler_isolated(db, kaydan_tenant, site_chantier, employee, worker):
    """Le handler BADGE_LOAN détecte 2 holders distincts pour un même badge."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import _handler_badge_loan

    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="LOAN-1",
        holder_kind="employee", holder_object_id=employee.id,
        decision="granted", method="nfc",
    )
    second = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="LOAN-1",
        holder_kind="worker", holder_object_id=worker.id,
        decision="granted", method="nfc",
    )
    rule = FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_LOAN",
        name="Badge prêté", severity="high", is_active=True, parameters={},
    )
    evidence = _handler_badge_loan(second, rule)
    assert evidence is not None
    assert evidence["badge_uid"] == "LOAN-1"
    assert evidence["first_holder_kind"] == "employee"


@pytest.mark.integration
def test_badge_twice_in_handler(db, kaydan_tenant, site_chantier):
    """Deux entrées consécutives même badge sans sortie en 60min déclenchent."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import _handler_badge_twice_in

    now = timezone.now()
    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now - timedelta(minutes=20), badge_uid="DUP-1",
        direction="in", decision="granted", method="nfc",
    )
    second = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now, badge_uid="DUP-1",
        direction="in", decision="granted", method="nfc",
    )
    rule = FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_TWICE_IN",
        name="Double entrée", severity="medium", is_active=True,
        parameters={"window_min": 60},
    )
    evidence = _handler_badge_twice_in(second, rule)
    assert evidence is not None
    assert evidence["badge_uid"] == "DUP-1"


@pytest.mark.integration
def test_badge_twice_in_resets_after_out(db, kaydan_tenant, site_chantier):
    """Si une sortie a eu lieu entre les 2 entrées, pas d'alerte."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import _handler_badge_twice_in

    now = timezone.now()
    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now - timedelta(minutes=30), badge_uid="DUP-2",
        direction="in", decision="granted", method="nfc",
    )
    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now - timedelta(minutes=15), badge_uid="DUP-2",
        direction="out", decision="granted", method="nfc",
    )
    second_in = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now, badge_uid="DUP-2",
        direction="in", decision="granted", method="nfc",
    )
    rule = FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_TWICE_IN",
        name="Double entrée", severity="medium", is_active=True, parameters={},
    )
    assert _handler_badge_twice_in(second_in, rule) is None


@pytest.mark.integration
def test_out_of_hours_handler(db, kaydan_tenant, site_chantier):
    from datetime import datetime, time as dtime

    from django.utils import timezone

    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import _handler_out_of_hours

    # Force un timestamp à 23:30 local
    ts = timezone.localtime().replace(hour=23, minute=30, second=0, microsecond=0)
    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=ts, badge_uid="NIGHT-1",
        direction="in", decision="granted", method="nfc",
    )
    rule = FraudRule.objects.create(
        tenant=kaydan_tenant, code="OUT_OF_HOURS",
        name="Hors plage", severity="high", is_active=True,
        parameters={"start": "06:00", "end": "20:00"},
    )
    evidence = _handler_out_of_hours(ev, rule)
    assert evidence is not None
    assert "scan_time" in evidence


@pytest.mark.integration
def test_ghost_helmet_handler(db, kaydan_tenant, site_chantier):
    """Helmet scanné sans badge = ouvrier qui pose le casque sans badger."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import _handler_ghost_helmet

    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), helmet_uid="HLM-001",
        # pas de badge_uid
        direction="in", decision="granted", method="uhf",
    )
    rule = FraudRule.objects.create(
        tenant=kaydan_tenant, code="GHOST_HELMET",
        name="Casque fantôme", severity="medium", is_active=True, parameters={},
    )
    evidence = _handler_ghost_helmet(ev, rule)
    assert evidence is not None
    assert evidence["helmet_uid"] == "HLM-001"


@pytest.mark.integration
def test_evaluate_inactive_rule_skipped(db, kaydan_tenant, access_event):
    """Une règle inactive ne doit pas se déclencher."""
    from antifraud.models import FraudAlert, FraudRule
    from antifraud.services import evaluate

    FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_LOAN",
        name="Inactive", severity="high", is_active=False, parameters={},
    )
    evaluate(access_event)
    assert FraudAlert.objects.count() == 0
