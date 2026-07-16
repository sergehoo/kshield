import pytest


@pytest.fixture
def badge_api_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        email="badges-api@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.mark.django_db
def test_badge_create_infers_tenant_and_maps_tech(
    api_client, badge_api_user, kaydan_tenant
):
    from core.models import Tenant
    from devices.models import Badge

    other_tenant = Tenant.objects.create(name="Autre tenant", code="other-badge")
    api_client.force_authenticate(badge_api_user)

    response = api_client.post(
        "/api/v1/devices/badges/",
        {
            "tenant": other_tenant.pk,
            "uid": "BADGE-API-UHF-001",
            "tech": "uhf",
        },
        format="json",
    )

    assert response.status_code == 201
    badge = Badge.objects.get(pk=response.json()["id"])
    assert badge.tenant_id == kaydan_tenant.pk
    assert badge.type == "uhf"
    assert badge.created_by_id == badge_api_user.pk
    assert response.json()["tenant"] == kaydan_tenant.pk
    assert response.json()["tech"] == "uhf"


@pytest.mark.django_db
def test_badge_create_rejects_duplicate_uid(
    api_client, badge_api_user, kaydan_tenant
):
    from devices.models import Badge

    Badge.objects.create(tenant=kaydan_tenant, uid="BADGE-API-DUP")
    api_client.force_authenticate(badge_api_user)

    response = api_client.post(
        "/api/v1/devices/badges/",
        {"uid": "BADGE-API-DUP", "tech": "nfc"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_badge_associate_and_dissociate_worker(
    api_client, badge_api_user, kaydan_tenant, worker
):
    from devices.models import Badge
    from devices.models_badges import BadgeAssignment

    badge = Badge.objects.create(
        tenant=kaydan_tenant,
        uid="BADGE-API-ASSOC",
        status="active",
    )
    api_client.force_authenticate(badge_api_user)

    associated = api_client.post(
        f"/api/v1/devices/badges/{badge.pk}/associate/",
        {"holder_kind": "worker", "holder_id": worker.pk},
        format="json",
    )

    assert associated.status_code == 201
    badge.refresh_from_db()
    assignment = BadgeAssignment.objects.get(
        badge=badge,
        closed_at__isnull=True,
    )
    assert badge.status == "assigned"
    assert badge.category == "worker_rfid"
    assert badge.holder == worker
    assert assignment.holder == worker

    dissociated = api_client.post(
        f"/api/v1/devices/badges/{badge.pk}/dissociate/",
        {},
        format="json",
    )

    assert dissociated.status_code == 200
    badge.refresh_from_db()
    assignment.refresh_from_db()
    assert badge.status == "available"
    assert badge.holder_object_id is None
    assert assignment.closed_at is not None
