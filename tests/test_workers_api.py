import pytest


@pytest.fixture
def company_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="workers-api@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.mark.django_db
def test_worker_create_infers_tenant_and_ignores_payload_tenant(
    api_client, company_user, kaydan_tenant
):
    from core.models import Tenant
    from ouvriers.models import Worker

    other_tenant = Tenant.objects.create(name="Autre tenant", code="other-worker")
    api_client.force_authenticate(company_user)

    response = api_client.post(
        "/api/v1/ouvriers/workers/",
        {
            "tenant": other_tenant.pk,
            "matricule": "OV-API-001",
            "first_name": "Awa",
            "last_name": "Kone",
        },
        format="json",
    )

    assert response.status_code == 201
    worker = Worker.objects.get(pk=response.json()["id"])
    assert worker.tenant_id == kaydan_tenant.pk
    assert response.json()["tenant"] == kaydan_tenant.pk
    assert worker.created_by_id == company_user.pk


@pytest.mark.django_db
def test_worker_create_rejects_duplicate_matricule_in_same_tenant(
    api_client, company_user, kaydan_tenant
):
    from ouvriers.models import Worker

    Worker.objects.create(
        tenant=kaydan_tenant,
        matricule="OV-API-DUP",
        first_name="Premier",
        last_name="Ouvrier",
    )
    api_client.force_authenticate(company_user)

    response = api_client.post(
        "/api/v1/ouvriers/workers/",
        {
            "matricule": "OV-API-DUP",
            "first_name": "Deuxième",
            "last_name": "Ouvrier",
        },
        format="json",
    )

    assert response.status_code == 400
