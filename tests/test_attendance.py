"""Tests pointage : punches, journées, congés, règles HS."""
from datetime import date, timedelta

import pytest
from django.utils import timezone


@pytest.mark.integration
def test_punch_creation(db, kaydan_tenant, site_chantier, employee):
    from django.contrib.contenttypes.models import ContentType

    from attendance.models import Punch
    from employees.models import Employee
    p = Punch.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(),
        holder_kind="employee",
        holder_content_type=ContentType.objects.get_for_model(Employee),
        holder_object_id=employee.id,
        type="in", status="ok",
    )
    assert p.id and p.holder_kind == "employee"
    assert p.delay_minutes == 0


@pytest.mark.integration
def test_punch_with_delay(db, kaydan_tenant, site_chantier, employee):
    from django.contrib.contenttypes.models import ContentType

    from attendance.models import Punch
    from employees.models import Employee
    p = Punch.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        timestamp=timezone.now(),
        holder_kind="employee",
        holder_content_type=ContentType.objects.get_for_model(Employee),
        holder_object_id=employee.id,
        type="in", status="late", delay_minutes=15,
    )
    assert p.delay_minutes == 15
    assert p.status == "late"


@pytest.mark.integration
def test_attendance_day_rollup(db, kaydan_tenant, site_chantier, employee):
    """AttendanceDay agrège les premiers/derniers punches du jour."""
    from attendance.models import AttendanceDay
    today = date.today()
    d = AttendanceDay.objects.create(
        tenant=kaydan_tenant, site=site_chantier,
        holder_kind="employee", holder_object_id=employee.id,
        date=today,
        first_punch_at=timezone.now().replace(hour=7, minute=55),
        last_punch_at=timezone.now().replace(hour=17, minute=10),
        duration_minutes=555,
        status="present",
    )
    assert d.duration_minutes == 555
    assert d.status == "present"


@pytest.mark.integration
def test_leave_request_lifecycle(db, employee):
    """Demande de congé créée → approuvée → durée calculable."""
    from attendance.models import LeaveRequest
    lr = LeaveRequest.objects.create(
        employee=employee, type="paid", status="pending",
        start_date=date.today(), end_date=date.today() + timedelta(days=4),
        reason="Vacances annuelles",
    )
    assert lr.status == "pending"
    assert (lr.end_date - lr.start_date).days == 4

    lr.status = "approved"
    lr.approved_at = timezone.now()
    lr.save()
    assert lr.status == "approved"


@pytest.mark.integration
def test_overtime_rule_active_filter(db, kaydan_company):
    from attendance.models import OvertimeRule
    OvertimeRule.objects.create(
        company=kaydan_company, name="Standard",
        weekly_threshold_hours=40,
        rate_125=1.25, rate_150=1.50, night_rate=1.50,
        is_active=True,
    )
    OvertimeRule.objects.create(
        company=kaydan_company, name="Old", is_active=False,
        weekly_threshold_hours=35, rate_125=1.25, rate_150=1.50, night_rate=1.50,
    )
    actives = OvertimeRule.objects.filter(is_active=True)
    assert actives.count() == 1


@pytest.mark.integration
def test_attendance_admin_page_renders(db, client):
    res = client.get("/attendance/")
    assert res.status_code == 200
    body = res.content.decode()
    assert "Punches" in body or "Pointage" in body


@pytest.mark.integration
def test_leave_request_create_via_admin(db, client, employee):
    from attendance.models import LeaveRequest
    res = client.post("/leave-requests/new/", {
        "employee": str(employee.id),
        "type": "paid", "status": "pending",
        "start_date": "2026-06-01", "end_date": "2026-06-05",
        "reason": "Test",
    })
    assert res.status_code in (302, 303)
    assert LeaveRequest.objects.count() == 1
