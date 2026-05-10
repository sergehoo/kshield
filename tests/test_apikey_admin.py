"""Tests UI gestion APIKeys (création one-shot + révoque)."""
import pytest
from django.test import Client


@pytest.mark.integration
def test_apikey_list_page_renders(db, client):
    res = client.get("/api-keys/")
    assert res.status_code == 200
    assert b"Cl" in res.content  # "Clés API"


@pytest.mark.integration
def test_apikey_create_displays_secret_once(db, kaydan_tenant):
    """Après POST /api-keys/new/, le redirect /api-keys/ affiche le secret
    UNE seule fois puis disparaît au reload suivant."""
    from accounts.models import APIKey
    c = Client()

    res = c.post("/api-keys/new/", {
        "name": "Gateway Site A",
        "scope": "device_terminal",
        "is_active": "on",
    }, follow=True)
    assert res.status_code == 200
    assert APIKey.objects.filter(name="Gateway Site A").exists()
    body = res.content.decode()
    assert "Secret API à copier maintenant" in body

    # Deuxième visite : le secret a disparu (session.pop)
    res2 = c.get("/api-keys/")
    assert "Secret API à copier maintenant" not in res2.content.decode()


@pytest.mark.integration
def test_apikey_secret_only_hash_stored(db, kaydan_tenant):
    """Le secret brut n'est JAMAIS stocké en base — seul le hash."""
    from accounts.models import APIKey
    c = Client()
    c.post("/api-keys/new/", {
        "name": "Test Hash",
        "scope": "device_terminal",
        "is_active": "on",
    })
    k = APIKey.objects.get(name="Test Hash")
    # secret_hash est un hex SHA-256 (64 caractères)
    assert len(k.secret_hash) == 64
    assert all(c in "0123456789abcdef" for c in k.secret_hash)


@pytest.mark.integration
def test_apikey_revoke_marks_inactive(db, kaydan_tenant):
    from accounts.models import APIKey
    k = APIKey.objects.create(
        tenant=kaydan_tenant, name="Test Revoke",
        scope="device_terminal", public_id="testpub123",
        secret_hash="0" * 64, is_active=True,
    )
    c = Client()
    res = c.post(f"/api-keys/{k.pk}/revoke/")
    assert res.status_code in (302, 303)
    k.refresh_from_db()
    assert k.is_active is False
    assert k.revoked_at is not None
