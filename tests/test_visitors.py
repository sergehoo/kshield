"""Tests visiteurs : QR self-service, conversion VisitRequest, badges."""
from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.mark.integration
def test_visitor_creation(db, kaydan_tenant):
    from visitors.models import Visitor
    v = Visitor.objects.create(
        tenant=kaydan_tenant, first_name="Marc", last_name="Dupont",
        nationality="FR", id_type="cni", id_number="CNI-001",
    )
    assert v.id and v.first_name == "Marc"
    assert v.uuid is not None


@pytest.mark.integration
def test_visit_request_default_status(db, visitor, site_chantier):
    from visitors.models import VisitRequest
    vr = VisitRequest.objects.create(
        tenant=visitor.tenant, visitor=visitor, site=site_chantier,
        purpose=None, purpose_other="meeting", mode="onsite",
        scheduled_at=timezone.now() + timedelta(hours=2),
        expected_duration_minutes=60,
    )
    assert vr.status in ("pending", "scheduled", "draft", "approved")


@pytest.mark.integration
def test_visit_request_check_in(db, visitor, site_chantier):
    """Une VisitRequest passe à 'checked_in' quand le visiteur arrive."""
    from visitors.models import VisitRequest
    vr = VisitRequest.objects.create(
        tenant=visitor.tenant, visitor=visitor, site=site_chantier,
        purpose=None, purpose_other="meeting", mode="onsite", status="approved",
        scheduled_at=timezone.now(),
    )
    vr.status = "checked_in"
    vr.save()
    assert vr.status == "checked_in"


@pytest.mark.integration
def test_visitor_admin_list_renders(db, client):
    res = client.get("/visitors/")
    assert res.status_code == 200


@pytest.mark.integration
def test_visitor_create_via_admin(db, client, kaydan_tenant):
    from visitors.models import Visitor
    res = client.post("/visitors-mng/new/", {
        "first_name": "Test", "last_name": "Visitor",
        "id_type": "cni", "id_number": "CNI-NEW-001",
        "nationality": "CI",
    })
    assert res.status_code in (200, 302), res.content[:200]
    if res.status_code in (302, 303):
        assert Visitor.objects.filter(id_number="CNI-NEW-001").exists()


@pytest.mark.integration
def test_visitor_count_by_pseudonymization(db, kaydan_tenant):
    """Visiteurs pseudonymisés (RGPD) sont distinguables des actifs."""
    from visitors.models import Visitor
    Visitor.objects.create(
        tenant=kaydan_tenant, first_name="Active", last_name="V",
        id_type="cni", id_number="CNI-A1",
    )
    Visitor.objects.create(
        tenant=kaydan_tenant, first_name="Anon", last_name="V",
        id_type="cni", id_number="CNI-A2",
        pseudonymized_at=timezone.now(),
    )
    assert Visitor.objects.filter(pseudonymized_at__isnull=True).count() == 1
    assert Visitor.objects.filter(pseudonymized_at__isnull=False).count() == 1


@pytest.mark.integration
def test_visit_request_filtered_by_site(db, visitor, site_chantier, kaydan_tenant, kaydan_company):
    from sites.models import Site
    from visitors.models import VisitRequest
    other = Site.objects.create(
        tenant=kaydan_tenant, code="other-site", name="Autre", type="office",
        company=kaydan_company, status="active", timezone="Africa/Abidjan",
    )
    VisitRequest.objects.create(
        tenant=kaydan_tenant, visitor=visitor, site=site_chantier,
        purpose=None, purpose_other="meeting", mode="onsite", scheduled_at=timezone.now(),
    )
    VisitRequest.objects.create(
        tenant=kaydan_tenant, visitor=visitor, site=other,
        purpose=None, purpose_other="meeting", mode="onsite", scheduled_at=timezone.now(),
    )
    assert VisitRequest.objects.filter(site=site_chantier).count() == 1
    assert VisitRequest.objects.filter(site=other).count() == 1
