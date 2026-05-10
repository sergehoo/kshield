"""Tests RBAC : login required + permissions par rôle."""
import pytest
from django.test import Client


@pytest.mark.integration
def test_anon_redirected_to_login_on_dashboard(db, client_anon):
    res = client_anon.get("/")
    assert res.status_code == 302
    assert "/auth/login/" in res["Location"]


@pytest.mark.integration
def test_anon_redirected_on_employees(db, client_anon):
    res = client_anon.get("/employees/")
    assert res.status_code == 302
    assert "/auth/login/" in res["Location"]


@pytest.mark.integration
def test_login_view_renders_get(db, client_anon):
    res = client_anon.get("/auth/login/")
    assert res.status_code == 200
    assert b"KAYDAN" in res.content


@pytest.mark.integration
def test_login_authenticates_then_redirects(db, client_anon):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(email="rbac@kaydan.test", password="StrongPw1234")
    res = client_anon.post("/auth/login/", {
        "email": "rbac@kaydan.test", "password": "StrongPw1234", "next": "/",
    })
    assert res.status_code == 302
    assert res["Location"] in ("/", "/admin-dashboard")


@pytest.mark.integration
def test_login_rejects_bad_password(db, client_anon):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(email="bad@kaydan.test", password="GoodOne1")
    res = client_anon.post("/auth/login/", {
        "email": "bad@kaydan.test", "password": "WrongOne1",
    })
    assert res.status_code == 200
    assert b"invalide" in res.content.lower()


@pytest.mark.integration
def test_login_attempt_recorded(db, client_anon):
    from accounts.models import LoginAttempt
    client_anon.post("/auth/login/", {
        "email": "ghost@kaydan.test", "password": "x",
    })
    assert LoginAttempt.objects.filter(
        email="ghost@kaydan.test", success=False).exists()


@pytest.mark.integration
def test_user_without_perm_redirected(db, client_anon):
    """Un user sans permission antifraud.view est refoulé du module audit."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(email="op@kaydan.test", password="x")
    client_anon.force_login(u)
    res = client_anon.get("/audit/", follow=False)
    # Redirige vers /admin-dashboard avec messages d'erreur
    assert res.status_code == 302


@pytest.mark.integration
def test_user_with_perm_can_access(db, client_anon):
    """Un user avec audit.view atteint /audit/."""
    from django.contrib.auth import get_user_model

    from accounts.models import Role, RoleAssignment, RolePermission
    User = get_user_model()
    u = User.objects.create_user(email="audit@kaydan.test", password="x")
    role = Role.objects.create(code="auditor", name="Auditeur", scope="tenant")
    RolePermission.objects.create(role=role, code="audit.view")
    RoleAssignment.objects.create(user=u, role=role)
    client_anon.force_login(u)
    res = client_anon.get("/audit/")
    assert res.status_code == 200


@pytest.mark.integration
def test_superuser_bypasses_rbac(db, client):
    """Le client autouse fixture est superuser → toutes les pages sensibles OK."""
    for url in ("/audit/", "/api-keys/", "/accounts/"):
        res = client.get(url)
        assert res.status_code == 200, f"failed {url}: {res.status_code}"


@pytest.mark.integration
def test_module_wildcard_permission(db, client_anon):
    """`employees.*` couvre `employees.view`."""
    from accounts.rbac import user_has_permission
    from django.contrib.auth import get_user_model

    from accounts.models import Role, RoleAssignment, RolePermission
    User = get_user_model()
    u = User.objects.create_user(email="wc@kaydan.test", password="x")
    role = Role.objects.create(code="hr", name="RH", scope="tenant")
    RolePermission.objects.create(role=role, code="employees.*")
    RoleAssignment.objects.create(user=u, role=role)
    assert user_has_permission(u, "employees.view") is True
    assert user_has_permission(u, "employees.manage") is True
    assert user_has_permission(u, "audit.view") is False


@pytest.mark.integration
def test_role_form_saves_checkboxes(db, client):
    from accounts.models import Role, RolePermission
    res = client.post("/roles/new/", {
        "code": "spv", "name": "Superviseur", "scope": "site",
        "description": "Test",
        "permissions_codes": ["employees.view", "workers.view", "antifraud.view"],
        "permissions_text": "custom.tool",
    })
    assert res.status_code in (302, 303), res.content[:200]
    role = Role.objects.get(code="spv")
    codes = set(role.permissions.values_list("code", flat=True))
    assert "employees.view" in codes
    assert "workers.view" in codes
    assert "antifraud.view" in codes
    assert "custom.tool" in codes
