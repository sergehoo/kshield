import io
import zipfile

import pytest


@pytest.fixture
def gateway(db, kaydan_tenant, site_chantier):
    from devices.models import LocalAgent

    return LocalAgent.objects.create(
        tenant=kaydan_tenant,
        site=site_chantier,
        label="Gateway Test",
        api_token="api-token-download-test",
        hmac_secret="hmac-secret-download-test",
        activation_token="initial-token",
    )


@pytest.fixture
def admin_user(db, kaydan_tenant):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="edge-admin@kaydan.test",
        password="x",
        tenant=kaydan_tenant,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def company_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="edge-company-user@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
        is_staff=True,
    )


def test_gateway_download_package_returns_installable_zip(api_client, admin_user, gateway):
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        f"/api/v1/devices/edge-gateway/{gateway.pk}/download/",
        {"platform": "linux_sh"},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Kshield-Gateway-Id"] == str(gateway.pk)
    assert response["X-Kshield-Platform"] == "linux_sh"

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
        assert "config/kshield-agent.toml" in names
        assert "install-edge.sh" in names
        assert "README.txt" in names
        assert "VERSION.json" in names

        config = zf.read("config/kshield-agent.toml").decode()
        assert f'id               = "{gateway.pk}"' in config
        assert 'activation_token = "' in config
        assert 'server_url       = "' in config

        install_script = zf.read("install-edge.sh").decode()
        assert "BUNDLED_CONFIG" in install_script
        assert "read_toml_value" in install_script

        manifest = zf.read("VERSION.json").decode()
        assert "/api/v1/devices/edge-gateway/updates/check/" in manifest


def test_gateway_download_route_accepts_api_returned_integer_id(
    api_client, admin_user, gateway
):
    api_client.force_authenticate(admin_user)

    detail = api_client.get(f"/api/v1/devices/edge-gateway/{gateway.pk}/")

    assert detail.status_code == 200
    assert detail.json()["id"] == str(gateway.pk)


def test_gateway_endpoints_resolve_tenant_from_company(
    api_client, company_user, gateway
):
    api_client.force_authenticate(company_user)

    detail = api_client.get(f"/api/v1/devices/edge-gateway/{gateway.pk}/")
    logs = api_client.get(f"/api/v1/devices/edge-gateway/{gateway.pk}/logs/")
    targets = api_client.get(f"/api/v1/devices/edge-gateway/{gateway.pk}/targets/")

    assert detail.status_code == 200
    assert logs.status_code == 200
    assert targets.status_code == 200
    assert targets.json() == {"count": 0, "targets": []}


def test_gateway_target_uses_deployed_uuid_schema(api_client, company_user, gateway):
    api_client.force_authenticate(company_user)

    created = api_client.post(
        f"/api/v1/devices/edge-gateway/{gateway.pk}/targets/",
        {
            "vendor": "hikvision",
            "ip": "192.0.2.20",
            "port": 80,
            "label": "Portail test",
        },
        format="json",
    )

    assert created.status_code == 201
    target_id = created.json()["id"]

    detail = api_client.get(
        f"/api/v1/devices/edge-gateway/{gateway.pk}/targets/{target_id}/"
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == target_id
