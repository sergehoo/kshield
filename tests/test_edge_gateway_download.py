import io
import hashlib
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


@pytest.mark.parametrize(
    ("platform", "binary_name", "installer_name"),
    [
        ("linux_amd64_go", "kshield-agent-linux-amd64", "install-edge-go.sh"),
        (
            "windows_amd64_go",
            "kshield-agent-windows-amd64.exe",
            "install-edge-go.ps1",
        ),
    ],
)
def test_go_gateway_download_embeds_verified_native_binary(
    api_client, admin_user, gateway, platform, binary_name, installer_name
):
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        f"/api/v1/devices/edge-gateway/{gateway.pk}/download/",
        {"platform": platform},
    )

    assert response.status_code == 200, response.content[:500]
    assert response["X-Kshield-Platform"] == platform
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert zf.testzip() is None
        assert installer_name in zf.namelist()
        binary = zf.read(f"bin/{binary_name}")
        checksum_line = zf.read("bin/SHA256SUMS.txt").decode().strip()
        assert len(binary) > 1_000_000
        assert checksum_line == f"{hashlib.sha256(binary).hexdigest()}  {binary_name}"


def test_activated_gateway_download_contains_reinstall_credentials(
    api_client, admin_user, gateway
):
    from django.utils import timezone

    gateway.activated_at = timezone.now()
    gateway.activation_token = None
    gateway.save(update_fields=["activated_at", "activation_token"])
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        f"/api/v1/devices/edge-gateway/{gateway.pk}/download/",
        {"platform": "linux_amd64_go"},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        config = zf.read("config/kshield-agent.toml").decode()
        assert f'api_token         = "{gateway.api_token}"' in config
        assert f'hmac_secret       = "{gateway.hmac_secret}"' in config
        assert 'activation_token = ""' in config


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


def test_activate_returns_mqtt_credentials(api_client, kaydan_tenant, settings):
    """Contract test — /activate/ doit renvoyer les credentials MQTT
    Option A (username + password) pour que l'agent Go puisse se connecter
    à EMQX. Sans ce contrat, l'agent reconnecte en boucle sur 'auth failed'.
    """
    from devices.models import LocalAgent

    settings.MQTT_AGENT_USERNAME = "kshield-edge-master"
    settings.MQTT_AGENT_PASSWORD = "super-secret-broker-pw"
    settings.MQTT_PUBLIC_HOST = "mqtt.example.com"
    settings.MQTT_PUBLIC_PORT = 8883
    settings.MQTT_TLS = True

    gw = LocalAgent.objects.create(
        tenant=kaydan_tenant,
        label="Gateway Activate Test",
        activation_token="tok-activate-test",
    )

    resp = api_client.post(
        "/api/v1/devices/edge-gateway/activate/",
        {
            "activation_token": "tok-activate-test",
            "system_info": {"os": "linux", "arch": "amd64",
                            "hostname": "gw-01", "agent_version": "1.2.0"},
        },
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    # Contrat critique — sans ces champs, l'agent Go crash au boot.
    assert body["success"] is True
    assert body["api_token"]
    assert body["hmac_secret"]
    assert body["mqtt_host"] == "mqtt.example.com"
    assert body["mqtt_port"] == 8883
    assert body["mqtt_use_tls"] is True
    assert body["mqtt_username"] == "kshield-edge-master"
    assert body["mqtt_password"] == "super-secret-broker-pw"

    gw.refresh_from_db()
    assert gw.activated_at is not None
    assert gw.activation_token in (None, "")


def test_activate_falls_back_to_backend_credentials(api_client, kaydan_tenant, settings):
    """Si MQTT_AGENT_* est vide, l'endpoint tombe sur MQTT_USERNAME/PASSWORD
    (compte partagé avec le backend) au lieu de renvoyer un password vide.
    """
    from devices.models import LocalAgent

    settings.MQTT_AGENT_USERNAME = ""
    settings.MQTT_AGENT_PASSWORD = ""
    settings.MQTT_USERNAME = "kshield-backend"
    settings.MQTT_PASSWORD = "backend-pw"

    gw = LocalAgent.objects.create(
        tenant=kaydan_tenant, label="Fallback", activation_token="tok-fallback",
    )

    resp = api_client.post(
        "/api/v1/devices/edge-gateway/activate/",
        {"activation_token": "tok-fallback"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["mqtt_username"] == "kshield-backend"
    assert body["mqtt_password"] == "backend-pw"
