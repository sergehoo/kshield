"""Tests authentification, rôles, permissions, JWT."""
import pytest


@pytest.mark.integration
def test_user_create_with_email_as_username(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(email="alice@kaydan.test", password="MotDePasse123")
    assert u.email == "alice@kaydan.test"
    assert u.check_password("MotDePasse123")
    assert u.is_active is True
    assert u.is_staff is False


@pytest.mark.integration
def test_user_create_superuser(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_superuser(email="root@kaydan.test", password="root12345678")
    assert u.is_staff is True
    assert u.is_superuser is True


@pytest.mark.integration
def test_login_endpoint_returns_jwt(db, api_client):
    """POST /api/v1/auth/login/ retourne access + refresh + user."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(email="bob@kaydan.test", password="SecretPass1")
    res = api_client.post("/api/v1/auth/login/",
                           {"email": "bob@kaydan.test", "password": "SecretPass1"},
                           format="json")
    assert res.status_code == 200, res.content
    assert "access" in res.data
    assert "refresh" in res.data


@pytest.mark.integration
def test_login_rejects_wrong_password(db, api_client):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(email="charlie@kaydan.test", password="GoodPass1")
    res = api_client.post("/api/v1/auth/login/",
                           {"email": "charlie@kaydan.test", "password": "WrongPass1"},
                           format="json")
    assert res.status_code == 400  # serializer error


@pytest.mark.integration
def test_login_attempt_logged(db, api_client):
    """Chaque tentative de login crée une LoginAttempt traçable."""
    from accounts.models import LoginAttempt
    api_client.post("/api/v1/auth/login/",
                     {"email": "ghost@kaydan.test", "password": "x"},
                     format="json")
    assert LoginAttempt.objects.filter(email="ghost@kaydan.test", success=False).exists()


@pytest.mark.integration
def test_drf_endpoint_requires_authentication(db, api_client):
    """Sans token JWT, GET /api/v1/employees/ doit refuser."""
    res = api_client.get("/api/v1/employees/employees/")
    assert res.status_code in (401, 403, 404)
    assert res.status_code != 200


@pytest.mark.integration
def test_role_creation_with_permissions(db):
    from accounts.models import Role, RolePermission
    role = Role.objects.create(code="security_officer", name="Officier sécurité",
                                 scope="site", is_system=False)
    RolePermission.objects.create(role=role, code="antifraud.acknowledge_alert")
    RolePermission.objects.create(role=role, code="badges.scan")
    assert role.permissions.count() == 2
    assert set(role.permissions.values_list("code", flat=True)) == {
        "antifraud.acknowledge_alert", "badges.scan",
    }


@pytest.mark.integration
def test_role_assignment_links_user_role_site(db, kaydan_tenant, site_chantier):
    from django.contrib.auth import get_user_model

    from accounts.models import Role, RoleAssignment
    User = get_user_model()
    u = User.objects.create_user(email="dave@kaydan.test", password="x12345678")
    role = Role.objects.create(code="supervisor", name="Superviseur", scope="site")
    a = RoleAssignment.objects.create(user=u, role=role, site=site_chantier)
    assert a.user_id == u.id
    assert a.role_id == role.id
    assert u.role_assignments.count() == 1


@pytest.mark.integration
def test_admin_accounts_page_renders(db, client):
    res = client.get("/accounts/")
    assert res.status_code in (200, 302)


@pytest.mark.integration
def test_user_password_reset_via_admin_view(db, client):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(email="reset@kaydan.test", password="OldOne123")
    res = client.post(f"/accounts/{u.pk}/password/", {
        "password": "NouveauMdp456",
        "password_confirm": "NouveauMdp456",
    })
    assert res.status_code in (302, 303)
    u.refresh_from_db()
    assert u.check_password("NouveauMdp456")


@pytest.mark.integration
def test_user_toggle_active_endpoint(db, client):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(email="toggle@kaydan.test", password="x12345678")
    assert u.is_active is True
    res = client.post(f"/accounts/{u.pk}/toggle/")
    assert res.status_code in (302, 303)
    u.refresh_from_db()
    assert u.is_active is False
