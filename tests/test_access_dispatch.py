"""Tests : pipeline de dispatch async (anti-fraude + notifications)."""
import pytest
from django.utils import timezone


@pytest.mark.integration
def test_evaluate_returns_empty_when_no_rules(db, kaydan_tenant, site_chantier, employee):
    """Sans règle active, evaluate() ne crée aucune alerte."""
    from access_control.models import AccessEvent
    from antifraud.services import evaluate

    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="B-001",
        decision="granted", method="nfc",
        holder_kind="employee", holder_object_id=employee.id,
    )
    alerts = evaluate(ev)
    assert alerts == []


@pytest.mark.integration
def test_badge_loan_rule_triggers_alert(db, kaydan_tenant, site_chantier, employee, worker):
    """Si le même badge est utilisé par 2 holders distincts le même jour,
    la règle BADGE_LOAN crée une FraudAlert."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudAlert, FraudRule
    from antifraud.services import evaluate

    FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_LOAN",
        name="Badge prêté", severity="high",
        is_active=True, parameters={},
    )

    now = timezone.now()
    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now, badge_uid="SHARED-001",
        decision="granted", method="nfc",
        holder_kind="employee", holder_object_id=employee.id,
    )
    second = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=now, badge_uid="SHARED-001",
        decision="granted", method="nfc",
        holder_kind="worker", holder_object_id=worker.id,
    )
    alerts = evaluate(second)
    assert len(alerts) == 1
    assert alerts[0].rule.code == "BADGE_LOAN"
    assert FraudAlert.objects.count() == 1


@pytest.mark.integration
def test_dispatch_creates_notifications_for_alerts(db, kaydan_tenant, site_chantier, employee, worker):
    """Le task dispatch_access_event évalue les règles ET dispatch les notifs."""
    from django.contrib.auth import get_user_model

    from access_control.models import AccessEvent
    from access_control.tasks import dispatch_access_event
    from antifraud.models import FraudRule
    from notifications.models import Notification

    User = get_user_model()
    User.objects.create_user(email="security@kaydan.test", password="x12345678",
                              is_staff=True, is_active=True)

    FraudRule.objects.create(
        tenant=kaydan_tenant, code="BADGE_LOAN",
        name="Badge prêté", severity="high",
        is_active=True, parameters={},
    )

    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="SHARED-002",
        decision="granted", method="nfc",
        holder_kind="employee", holder_object_id=employee.id,
    )
    second = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="SHARED-002",
        decision="granted", method="nfc",
        holder_kind="worker", holder_object_id=worker.id,
    )

    # En dev CELERY_TASK_ALWAYS_EAGER=True donc apply directement
    result = dispatch_access_event(second.id)

    assert len(result["alerts"]) == 1
    assert result["notifications"] >= 1
    assert Notification.objects.filter(
        subject__icontains="Alerte anti-fraude",
    ).exists()


@pytest.mark.integration
def test_dispatch_handles_missing_event_gracefully(db):
    from access_control.tasks import dispatch_access_event
    result = dispatch_access_event(999_999)
    assert result["status"] == "missing"


@pytest.mark.integration
def test_denied_access_creates_notification_without_rule(db, kaydan_tenant, site_chantier):
    """Un accès refusé sans règle anti-fraude génère quand même une notif."""
    from django.contrib.auth import get_user_model

    from access_control.models import AccessEvent
    from access_control.tasks import dispatch_access_event
    from notifications.models import Notification

    User = get_user_model()
    User.objects.create_user(email="ops@kaydan.test", password="x12345678",
                              is_staff=True, is_active=True)

    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="DENIED-001",
        decision="denied", denial_reason="BADGE_INCONNU",
        method="nfc",
    )
    result = dispatch_access_event(ev.id)
    assert result["notifications"] >= 1
    assert Notification.objects.filter(
        subject__icontains="Accès refusé",
    ).exists()
