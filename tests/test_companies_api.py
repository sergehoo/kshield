import pytest


@pytest.fixture
def company_api_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="companies-api@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.mark.django_db
def test_company_create_infers_tenant_and_ignores_payload_tenant(
    api_client, company_api_user, kaydan_tenant
):
    from core.models import Company, Tenant

    other_tenant = Tenant.objects.create(name="Autre tenant", code="other-company")
    api_client.force_authenticate(company_api_user)

    response = api_client.post(
        "/api/v1/core/companies/",
        {
            "tenant": other_tenant.pk,
            "name": "Nouvelle filiale",
            "code": "new-company",
            "sector": "services",
        },
        format="json",
    )

    assert response.status_code == 201
    company = Company.objects.get(pk=response.json()["id"])
    assert company.tenant_id == kaydan_tenant.pk
    assert response.json()["tenant"] == kaydan_tenant.pk
    assert company.created_by_id == company_api_user.pk


@pytest.mark.django_db
def test_company_create_rejects_duplicate_code_in_same_tenant(
    api_client, company_api_user, kaydan_tenant
):
    from core.models import Company

    Company.objects.create(
        tenant=kaydan_tenant,
        name="Filiale existante",
        code="duplicate-company",
    )
    api_client.force_authenticate(company_api_user)

    response = api_client.post(
        "/api/v1/core/companies/",
        {
            "name": "Autre filiale",
            "code": "duplicate-company",
        },
        format="json",
    )

    assert response.status_code == 400
