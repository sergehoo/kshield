"""Smoke tests : pages admin + endpoints."""
import pytest


@pytest.mark.integration
def test_dashboard_renders(db, client):
    r = client.get("/")
    assert r.status_code == 200


@pytest.mark.integration
def test_badges_list_renders(db, client):
    r = client.get("/badges/")
    assert r.status_code == 200


@pytest.mark.integration
def test_badge_detail_renders(db, kaydan_tenant, kaydan_company, client):
    from devices.services import BadgeWorkflowService
    from employees.models import Employee
    emp = Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-SMK", first_name="Smoke", last_name="Test",
        contract_type="cdi", status="active", work_location="office",
    )
    badge = BadgeWorkflowService.issue_employee_badge(emp)
    res = client.get(f"/badges-mng/{badge.pk}/")
    assert res.status_code == 200
    body = res.content.decode()
    assert badge.uid in body


@pytest.mark.integration
def test_badge_thumbnail_endpoint_returns_png(db, kaydan_tenant, kaydan_company, client):
    from devices.services import BadgeWorkflowService
    from employees.models import Employee
    emp = Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-THB", first_name="Thumb", last_name="Nail",
        contract_type="cdi", status="active", work_location="office",
    )
    badge = BadgeWorkflowService.issue_employee_badge(emp)
    res = client.get(f"/badges/{badge.pk}/thumbnail/")
    assert res.status_code == 200
    assert res["Content-Type"] == "image/png"
    assert res.content[:4] == b"\x89PNG"


@pytest.mark.integration
def test_badge_pdf_endpoint(db, kaydan_tenant, kaydan_company, client):
    from devices.services import BadgeWorkflowService
    from employees.models import Employee
    emp = Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-PDF", first_name="Pdf", last_name="Test",
        contract_type="cdi", status="active", work_location="office",
    )
    badge = BadgeWorkflowService.issue_employee_badge(emp)
    res = client.get(f"/badges/{badge.pk}/pdf/")
    assert res.status_code == 200
    assert res["Content-Type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"


@pytest.mark.integration
def test_user_create_view_creates_user(db, kaydan_tenant, client):
    res = client.post("/accounts/new/", {
        "email": "test.user@kaydangroupe.com",
        "first_name": "Test",
        "last_name": "User",
        "phone": "+225 07 00 00 00 00",
        "password": "SuperSecret123",
        "password_confirm": "SuperSecret123",
        "is_active": "on",
    })
    assert res.status_code in (302, 303), res.content[:200]
    from django.contrib.auth import get_user_model
    u = get_user_model().objects.get(email="test.user@kaydangroupe.com")
    assert u.check_password("SuperSecret123")


@pytest.mark.integration
def test_user_password_change(db, client):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(email="reset@kaydangroupe.com", password="OldPass123")
    res = client.post(f"/accounts/{u.pk}/password/", {
        "password": "NewPass456",
        "password_confirm": "NewPass456",
    })
    assert res.status_code in (302, 303)
    u.refresh_from_db()
    assert u.check_password("NewPass456")


@pytest.mark.integration
def test_role_create_with_permissions(db, client):
    res = client.post("/roles/new/", {
        "code": "controleur",
        "name": "Contrôleur de site",
        "scope": "site",
        "permissions_text": "antifraud.acknowledge_alert\nemployees.view\nbadges.scan",
    })
    assert res.status_code in (302, 303)
    from accounts.models import Role
    r = Role.objects.get(code="controleur")
    assert r.permissions.count() == 3


@pytest.mark.integration
def test_company_detail_shows_counts(db, kaydan_company, client):
    res = client.get(f"/companies-mng/{kaydan_company.pk}/")
    assert res.status_code == 200
    body = res.content.decode()
    assert kaydan_company.name in body
    assert "Employés" in body
    assert "Ouvriers" in body


@pytest.mark.integration
def test_company_form_has_logo_field(db, kaydan_company, client):
    res = client.get(f"/companies-mng/{kaydan_company.pk}/edit/")
    assert res.status_code == 200
    body = res.content.decode()
    assert 'name="logo"' in body
    assert 'enctype="multipart/form-data"' in body


@pytest.mark.integration
def test_workers_list_renders(db, kaydan_tenant, worker, client):
    from devices.models import Helmet
    from devices.services import BadgeWorkflowService
    helmet = Helmet.objects.create(
        tenant=kaydan_tenant, serial_number="HLM-LIST",
        uhf_tag_uid="UHF-LIST", ble_beacon_uid="BLE-LIST", status="active",
    )
    BadgeWorkflowService.issue_worker_badge(worker, helmet=helmet)
    res = client.get("/workers/")
    assert res.status_code == 200


@pytest.mark.integration
def test_map_view_renders(db, client):
    res = client.get("/map/")
    assert res.status_code == 200
    body = res.content.decode()
    assert "leaflet" in body.lower()


@pytest.mark.integration
def test_map_data_api(db, client):
    res = client.get("/map/data/")
    assert res.status_code == 200
    data = res.json()
    assert "sites" in data
    assert "stats" in data


@pytest.mark.integration
def test_realtime_view_renders(db, client):
    res = client.get("/realtime/")
    assert res.status_code == 200
    body = res.content.decode()
    assert 'name="period"' in body


@pytest.mark.integration
def test_realtime_excel_export(db, kaydan_tenant, site_chantier, employee, client):
    from datetime import datetime

    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    from access_control.models import AccessEvent
    from employees.models import Employee
    AccessEvent.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(), badge_uid="EXP-001",
        decision="granted", method="nfc",
        holder_kind="employee",
        holder_content_type=ContentType.objects.get_for_model(Employee),
        holder_object_id=employee.id,
    )
    res = client.get("/realtime/export/?period=today")
    assert res.status_code == 200
    assert res.content[:4] == b"PK\x03\x04"  # ZIP/xlsx magic bytes


@pytest.mark.integration
def test_employees_list_with_filiale_filter(db, kaydan_tenant, kaydan_company, client):
    from core.models import Company
    from employees.models import Employee
    other = Company.objects.create(
        tenant=kaydan_tenant, code="kln", name="KAYDAN Logistique",
        sector="logistique", is_active=True,
    )
    Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-BTP", first_name="John", last_name="BTP",
        contract_type="cdi", status="active",
    )
    Employee.objects.create(
        tenant=kaydan_tenant, company=other,
        matricule="EMP-LOG", first_name="Jane", last_name="LOG",
        contract_type="cdi", status="active",
    )
    res = client.get(f"/employees/?company={other.id}")
    body = res.content.decode()
    assert "EMP-LOG" in body
    assert "EMP-BTP" not in body
