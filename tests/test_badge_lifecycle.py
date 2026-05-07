"""KAYDAN SHIELD — tests du cycle de vie complet des badges."""
import pytest

from devices.services import BadgeWorkflowService


@pytest.fixture
def helmet(db, kaydan_tenant):
    from devices.models import Helmet
    return Helmet.objects.create(
        tenant=kaydan_tenant, serial_number="HLM-TEST-001",
        uhf_tag_uid="UHF-001", ble_beacon_uid="BLE-001", status="active",
    )


@pytest.fixture
def employee_office(db, kaydan_tenant, kaydan_company):
    from employees.models import Employee
    return Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-OFF", first_name="Office", last_name="User",
        contract_type="cdi", status="active", work_location="office",
    )


@pytest.fixture
def employee_field(db, kaydan_tenant, kaydan_company):
    from employees.models import Employee
    return Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-FLD", first_name="Field", last_name="User",
        contract_type="cdi", status="active", work_location="field",
    )


@pytest.mark.integration
def test_create_visitor_qr_pool(db, kaydan_tenant):
    from devices.models import Badge
    badges = BadgeWorkflowService.create_visitor_qr_pool(count=3, prefix="QRT")
    assert len(badges) == 3
    for b in badges:
        assert b.category == "visitor_qr"
        assert b.status == "available"


@pytest.mark.integration
def test_issue_employee_office_no_helmet(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    assert badge.category == "employee_rfid"
    assert badge.status == "active"
    assert badge.paired_helmet is None


@pytest.mark.integration
def test_issue_employee_field_requires_helmet(db, kaydan_tenant, employee_field):
    with pytest.raises(ValueError):
        BadgeWorkflowService.issue_employee_badge(employee_field, helmet=None)


@pytest.mark.integration
def test_issue_employee_field_with_helmet(db, kaydan_tenant, employee_field, helmet):
    badge = BadgeWorkflowService.issue_employee_badge(employee_field, helmet=helmet)
    assert badge.paired_helmet == helmet
    assert badge.status == "active"


@pytest.mark.integration
def test_issue_worker_requires_helmet(db, kaydan_tenant, worker):
    with pytest.raises(ValueError):
        BadgeWorkflowService.issue_worker_badge(worker, helmet=None)


@pytest.mark.integration
def test_issue_worker_with_helmet(db, kaydan_tenant, worker, helmet):
    badge = BadgeWorkflowService.issue_worker_badge(worker, helmet=helmet)
    assert badge.category == "worker_rfid"
    assert badge.paired_helmet == helmet
    assert "BADGE:" in badge.qr_payload and "CASQUE:" in badge.qr_payload


@pytest.mark.integration
def test_suspend_then_reactivate(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    BadgeWorkflowService.suspend(badge, reason="enquête RH")
    assert badge.status == "suspended"
    assert badge.suspended_reason == "enquête RH"
    BadgeWorkflowService.reactivate(badge)
    assert badge.status == "active"


@pytest.mark.integration
def test_cannot_reactivate_revoked(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    BadgeWorkflowService.revoke(badge, reason="démission")
    with pytest.raises(ValueError):
        BadgeWorkflowService.reactivate(badge)


@pytest.mark.integration
def test_revoke_is_idempotent(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    BadgeWorkflowService.revoke(badge, reason="x")
    first_revoked_at = badge.revoked_at
    BadgeWorkflowService.revoke(badge, reason="y")
    assert badge.status == "revoked"
    assert badge.revoked_at == first_revoked_at


@pytest.mark.integration
def test_mark_lost_closes_assignment(db, kaydan_tenant, employee_office):
    from devices.models import BadgeAssignment
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    BadgeWorkflowService.mark_lost(badge, reason="oublié")
    assert badge.status == "lost"
    a = BadgeAssignment.objects.filter(badge=badge).order_by("-assigned_at").first()
    assert a.released_at is not None


@pytest.mark.integration
def test_release_employee_disables(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    BadgeWorkflowService.release(badge)
    assert badge.status == "disabled"


@pytest.mark.integration
def test_release_visitor_returns_to_pool(db, kaydan_tenant):
    [badge] = BadgeWorkflowService.create_visitor_qr_pool(count=1)
    badge.qr_payload = "VISIT-XYZ"
    badge.status = "active"
    badge.holder_kind = "visitor"
    badge.save()
    BadgeWorkflowService.release(badge)
    badge.refresh_from_db()
    assert badge.status == "available"
    assert badge.qr_payload == ""


@pytest.mark.integration
def test_can_be_used_truth_table(db, kaydan_tenant, employee_office):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    assert badge.can_be_used is True
    BadgeWorkflowService.suspend(badge)
    assert badge.can_be_used is False
    BadgeWorkflowService.reactivate(badge)
    assert badge.can_be_used is True
    BadgeWorkflowService.revoke(badge)
    assert badge.can_be_used is False


@pytest.mark.integration
def test_lookup_api_finds_by_uid(db, kaydan_tenant, employee_office, api_client):
    badge = BadgeWorkflowService.issue_employee_badge(employee_office)
    res = api_client.get(f"/api/v1/devices/badges/lookup/?q={badge.uid}")
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is True
    assert data["uid"] == badge.uid


@pytest.mark.integration
def test_lookup_api_404(db, api_client):
    res = api_client.get("/api/v1/devices/badges/lookup/?q=NOT-EXIST")
    assert res.status_code == 404
