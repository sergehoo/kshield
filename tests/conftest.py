"""KAYDAN SHIELD — Configuration pytest globale."""
import os
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kshield.settings.dev")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def kaydan_tenant(db):
    """Tenant singleton KAYDAN GROUPE."""
    from core.services import KaydanTenantService
    KaydanTenantService.reset_cache()
    return KaydanTenantService.get()


@pytest.fixture
def kaydan_company(db, kaydan_tenant):
    """Filiale KAYDAN BTP par défaut."""
    from core.models import Company
    c, _ = Company.objects.get_or_create(
        tenant=kaydan_tenant, code="kaydan-btp",
        defaults={"name": "KAYDAN BTP", "sector": "btp", "is_active": True},
    )
    return c


@pytest.fixture
def site_chantier(db, kaydan_tenant, kaydan_company):
    from sites.models import Site
    s, _ = Site.objects.get_or_create(
        tenant=kaydan_tenant, name="Chantier Test",
        defaults={"code": "chantier-test", "type": "construction",
                  "company": kaydan_company, "status": "active",
                  "timezone": "Africa/Abidjan"},
    )
    return s


@pytest.fixture
def employee(db, kaydan_tenant, kaydan_company):
    from employees.models import Employee
    return Employee.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        matricule="EMP-TEST-001", first_name="Aïcha", last_name="Bamba",
        email="aicha.bamba@kaydan.test", contract_type="cdi", status="active",
    )


@pytest.fixture
def worker(db, kaydan_tenant):
    from ouvriers.models import Trade, Worker
    trade, _ = Trade.objects.get_or_create(code="macon", defaults={"name": "Maçon"})
    return Worker.objects.create(
        tenant=kaydan_tenant, matricule="OV-TEST-001",
        first_name="Yao", last_name="Konan",
        trade=trade, status="active",
    )


@pytest.fixture
def visitor(db, kaydan_tenant):
    from visitors.models import Visitor
    return Visitor.objects.create(
        tenant=kaydan_tenant,
        first_name="Marc", last_name="Dupont",
        nationality="Française", id_type="cni", id_number="CNI-TEST-12345",
    )


@pytest.fixture
def device(db, kaydan_tenant, site_chantier):
    """Lecteur NFC fixe minimal pour les tests."""
    from devices.models import Device, DeviceModel
    model, _ = DeviceModel.objects.get_or_create(
        brand="Test", model="NFC-Reader-1",
        defaults={"type": "nfc_reader", "is_active": True},
    )
    return Device.objects.create(
        tenant=kaydan_tenant, model=model,
        serial_number="DEV-TEST-001",
        site=site_chantier, status="active",
    )


@pytest.fixture(autouse=True)
def _clear_caches(request):
    """Invalide les caches Django (notamment RBAC) entre tests."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _autologin_admin(db, request):
    """Log automatiquement le `client` Django en superuser sur tous les tests admin.

    Permet aux tests existants de continuer à passer après l'ajout du
    LoginRequired sur BaseAdminView. Désactivable en demandant la fixture
    `client_anon` (créée à la demande).
    """
    if "client_anon" in request.fixturenames:
        return
    from django.contrib.auth import get_user_model
    from django.test import Client
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        email="autotest@kaydan.test",
        defaults={"is_staff": True, "is_superuser": True, "is_active": True},
    )
    u.set_password("autotestpw")
    u.is_staff = True
    u.is_superuser = True
    u.is_active = True
    u.save()
    # Si le test a demandé `client`, on le pré-login
    if "client" in request.fixturenames:
        c = request.getfixturevalue("client")
        c.force_login(u)


@pytest.fixture
def client_anon(client):
    """Client Django anonyme (override du autologin pour tester l'auth)."""
    client.logout()
    return client


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def rf():
    from django.test import RequestFactory
    return RequestFactory()
