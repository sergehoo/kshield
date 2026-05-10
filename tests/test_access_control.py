"""Tests AccessGatewayService : pipeline scan complet."""
import pytest
from django.utils import timezone


@pytest.mark.integration
def test_scan_unknown_badge_returns_denied(db, device):
    from access_control.services import AccessGatewayService
    payload = {
        "device_serial": device.serial_number,
        "badge_uid": "UNKNOWN-XYZ",
        "method": "nfc",
    }
    event = AccessGatewayService.process_scan(payload)
    assert event.decision == "denied"
    assert event.denial_reason == "BADGE_INCONNU"


@pytest.mark.integration
def test_scan_with_active_employee_badge_granted(db, device, employee):
    from devices.services import BadgeWorkflowService

    from access_control.services import AccessGatewayService
    badge = BadgeWorkflowService.issue_employee_badge(employee)
    payload = {
        "device_serial": device.serial_number,
        "badge_uid": badge.uid,
        "method": "nfc",
    }
    event = AccessGatewayService.process_scan(payload)
    assert event.decision == "granted"
    assert event.holder_kind == "employee"


@pytest.mark.integration
def test_scan_with_revoked_badge_denied(db, device, employee):
    from devices.services import BadgeWorkflowService

    from access_control.services import AccessGatewayService
    badge = BadgeWorkflowService.issue_employee_badge(employee)
    badge.status = "revoked"
    badge.save()

    event = AccessGatewayService.process_scan({
        "device_serial": device.serial_number,
        "badge_uid": badge.uid,
        "method": "nfc",
    })
    assert event.decision == "denied"
    assert "REVOKED" in event.denial_reason.upper()


@pytest.mark.integration
def test_worker_scan_without_helmet_review(db, device, worker, kaydan_tenant):
    """Un ouvrier qui scanne uniquement le badge (sans helmet) renvoie 'review'."""
    from devices.models import Helmet
    from devices.services import BadgeWorkflowService

    from access_control.services import AccessGatewayService
    helmet = Helmet.objects.create(
        tenant=kaydan_tenant, serial_number="HLM-TST",
        uhf_tag_uid="UHF-TST", ble_beacon_uid="BLE-TST", status="active",
    )
    badge = BadgeWorkflowService.issue_worker_badge(worker, helmet=helmet)
    # Scan du badge SEUL (pas le casque) → CASQUE_MANQUANT
    event = AccessGatewayService.process_scan({
        "device_serial": device.serial_number,
        "badge_uid": badge.uid,
        "method": "nfc",
    })
    assert event.decision == "review"
    assert event.denial_reason == "CASQUE_MANQUANT"


@pytest.mark.integration
def test_scan_creates_access_decision(db, device):
    from access_control.models import AccessDecision
    from access_control.services import AccessGatewayService
    AccessGatewayService.process_scan({
        "device_serial": device.serial_number,
        "badge_uid": "ANOTHER-UNKNOWN",
        "method": "nfc",
    })
    assert AccessDecision.objects.count() == 1


@pytest.mark.integration
def test_access_rule_isactive_filter(db, kaydan_tenant, site_chantier):
    from access_control.models import AccessRule
    AccessRule.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        code="zone-restricted", name="Zone restreinte",
        type="zone_restriction", severity="high", is_active=True,
        conditions={}, actions={},
    )
    AccessRule.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        code="old", name="Old", type="time_restriction",
        severity="low", is_active=False,
        conditions={}, actions={},
    )
    assert AccessRule.objects.filter(is_active=True).count() == 1
