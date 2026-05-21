"""Tests SSO Keycloak — modèles, services, mappings, offline."""
import pytest
from django.utils import timezone
from datetime import timedelta


@pytest.mark.integration
def test_sso_identity_links_user(db):
    from django.contrib.auth import get_user_model
    from sso.models import SSOIdentity
    User = get_user_model()
    u = User.objects.create_user(email="kc@kaydan.test", password="x")
    ident = SSOIdentity.objects.create(
        user=u, subject="abc-123-keycloak", issuer="https://auth.test/realms/kaydan",
        preferred_username="kc.user", email_verified=True,
    )
    assert ident.user == u
    assert ident.subject == "abc-123-keycloak"


@pytest.mark.integration
def test_sso_role_mapping_assigns_local_role(db):
    """Le service sync_user_roles applique les SSORoleMapping configurés."""
    from accounts.models import Role, RoleAssignment
    from django.contrib.auth import get_user_model
    from sso.models import SSORoleMapping
    from sso.services import sync_user_roles
    User = get_user_model()
    u = User.objects.create_user(email="r@kaydan.test", password="x")
    role = Role.objects.create(code="hr-supervisor", name="HR Sup", scope="tenant")
    SSORoleMapping.objects.create(
        keycloak_role="kaydan-hr-supervisor", local_role=role,
        auto_assign_on_login=True,
    )
    n = sync_user_roles(u, ["kaydan-hr-supervisor", "other-role-not-mapped"])
    assert n >= 1
    assert RoleAssignment.objects.filter(user=u, role=role).exists()


@pytest.mark.integration
def test_get_or_create_user_from_claims_creates_new(db, settings):
    settings.SSO_AUTO_CREATE_USER = True
    from sso.services import get_or_create_user_from_claims
    claims = {
        "sub": "new-user-sub-456",
        "email": "newuser@kaydan.test",
        "given_name": "New",
        "family_name": "User",
        "preferred_username": "newuser",
        "email_verified": True,
        "iss": "https://auth.test/realms/kaydan",
        "realm_access": {"roles": []},
    }
    user, created, ident = get_or_create_user_from_claims(claims)
    assert created is True
    assert user.email == "newuser@kaydan.test"
    assert ident.subject == "new-user-sub-456"


@pytest.mark.integration
def test_get_or_create_matches_existing_email(db):
    """Un user créé localement avant le SSO est lié au login Keycloak via email."""
    from django.contrib.auth import get_user_model
    from sso.models import SSOIdentity
    from sso.services import get_or_create_user_from_claims
    User = get_user_model()
    pre_existing = User.objects.create_user(
        email="existing@kaydan.test", password="local-pw",
        first_name="Pre", last_name="Existing",
    )
    claims = {
        "sub": "kc-sub-789", "email": "existing@kaydan.test",
        "given_name": "Pre", "family_name": "Existing",
        "iss": "https://auth.test/realms/kaydan",
    }
    user, created, ident = get_or_create_user_from_claims(claims)
    assert created is False
    assert user.pk == pre_existing.pk
    assert SSOIdentity.objects.filter(user=user, subject="kc-sub-789").exists()


@pytest.mark.integration
def test_disabled_user_blocked(db):
    """Un user désactivé localement ne peut pas se logger via SSO."""
    from django.contrib.auth import get_user_model
    from sso.services import get_or_create_user_from_claims
    User = get_user_model()
    User.objects.create_user(email="dis@kaydan.test", password="x", is_active=False)
    with pytest.raises(PermissionError):
        get_or_create_user_from_claims({
            "sub": "dis-1", "email": "dis@kaydan.test",
            "iss": "https://auth.test/realms/kaydan",
        })


@pytest.mark.integration
def test_sso_status_endpoint_anon(db, client_anon):
    res = client_anon.get("/sso/status/")
    assert res.status_code == 200
    data = res.json()
    assert "sso_enabled" in data
    assert data["authenticated"] is False


@pytest.mark.integration
def test_sso_status_endpoint_authenticated(db, client):
    res = client.get("/sso/status/")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["user"]["email"]


@pytest.mark.integration
def test_offline_login_with_pin(db, kaydan_tenant, site_chantier):
    """Un user avec un cache offline + PIN valide peut se logger sans serveur."""
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from sso.models import OfflineUserCredentialCache
    from sso.utils import hash_pin
    User = get_user_model()

    u = User.objects.create_user(email="edge@kaydan.test", password="x")
    OfflineUserCredentialCache.objects.create(
        user=u, site=site_chantier, pin_hash=hash_pin("1234"),
        permissions_snapshot=["badges.scan"], is_active=True,
        expires_at=timezone.now() + timedelta(hours=24),
    )
    from django.test import Client
    c = Client()
    res = c.post("/sso/offline-login/", {
        "email": "edge@kaydan.test", "pin": "1234", "site_id": site_chantier.id,
    })
    assert res.status_code == 200
    assert res.json()["ok"] is True


@pytest.mark.integration
def test_offline_login_rejects_bad_pin(db, kaydan_tenant, site_chantier):
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from sso.models import OfflineUserCredentialCache
    from sso.utils import hash_pin
    User = get_user_model()

    u = User.objects.create_user(email="edge2@kaydan.test", password="x")
    OfflineUserCredentialCache.objects.create(
        user=u, site=site_chantier, pin_hash=hash_pin("1234"),
        is_active=True, expires_at=timezone.now() + timedelta(hours=24),
    )
    from django.test import Client
    c = Client()
    res = c.post("/sso/offline-login/", {
        "email": "edge2@kaydan.test", "pin": "9999", "site_id": site_chantier.id,
    })
    assert res.status_code == 401


@pytest.mark.integration
def test_offline_cache_expired_rejected(db, kaydan_tenant, site_chantier):
    from django.contrib.auth import get_user_model
    from sso.models import OfflineUserCredentialCache
    from sso.utils import hash_pin
    User = get_user_model()
    u = User.objects.create_user(email="ex@kaydan.test", password="x")
    OfflineUserCredentialCache.objects.create(
        user=u, site=site_chantier, pin_hash=hash_pin("0000"),
        is_active=True, expires_at=timezone.now() - timedelta(hours=1),
    )
    from django.test import Client
    c = Client()
    res = c.post("/sso/offline-login/", {
        "email": "ex@kaydan.test", "pin": "0000", "site_id": site_chantier.id,
    })
    assert res.status_code == 401
    assert "expir" in res.json().get("error", "").lower()


@pytest.mark.integration
def test_sync_users_to_edge(db, kaydan_tenant, site_chantier):
    """sync_users_to_edge peuple le cache offline pour les users autorisés."""
    from accounts.models import Role, RoleAssignment
    from django.contrib.auth import get_user_model
    from sso.models import OfflineUserCredentialCache
    from sso.services import sync_users_to_edge
    User = get_user_model()
    u1 = User.objects.create_user(email="s1@kaydan.test", password="x")
    role = Role.objects.create(code="op", name="Op", scope="site")
    RoleAssignment.objects.create(user=u1, role=role, site=site_chantier)
    result = sync_users_to_edge(site_chantier, ttl_hours=24)
    assert result["pushed"] >= 1
    assert OfflineUserCredentialCache.objects.filter(
        user=u1, site=site_chantier, is_active=True).exists()


@pytest.mark.integration
def test_api_me_endpoint(db, client):
    res = client.get("/api/sso/me/")
    assert res.status_code == 200
    data = res.json()
    assert data["email"]
    assert isinstance(data["permissions"], list)
