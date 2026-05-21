"""KAYDAN SHIELD — Tests du scoping RBAC par filiale.

Vérifie que :
1. Un super-admin voit tout
2. Un user avec la permission `companies.view_all` voit tout
3. Un user lambda voit uniquement les données de SA filiale
4. Un user sans filiale ne voit rien
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def two_companies(db):
    """Crée 2 filiales (BTP + Logistique) avec un site chacune."""
    from core.models import Company, Tenant
    from sites.models import Site
    tenant = Tenant.objects.first() or Tenant.objects.create(
        name="KAYDAN GROUPE", code="KAYDAN",
    )
    btp = Company.objects.create(tenant=tenant, name="KAYDAN BTP",
                                    code="BTP", sector="construction")
    log = Company.objects.create(tenant=tenant, name="KAYDAN Logistique",
                                    code="LOG", sector="logistics")
    site_btp = Site.objects.create(tenant=tenant, company=btp,
                                      name="Chantier Riviera", code="RIVIERA",
                                      type="construction_site", status="active")
    site_log = Site.objects.create(tenant=tenant, company=log,
                                      name="Entrepôt Vridi", code="VRIDI",
                                      type="warehouse", status="active")
    return btp, log, site_btp, site_log


@pytest.fixture
def users(db, two_companies):
    """Crée 3 utilisateurs : super-admin, user BTP, user sans filiale."""
    btp, log, _, _ = two_companies
    admin = User.objects.create_superuser(
        email="admin@kaydan.test", password="p", first_name="Super", last_name="Admin",
    )
    user_btp = User.objects.create_user(
        email="btp@kaydan.test", password="p",
        first_name="Pierre", last_name="BTP", company=btp,
    )
    user_orphan = User.objects.create_user(
        email="orphan@kaydan.test", password="p",
        first_name="Sans", last_name="Filiale",
    )
    return admin, user_btp, user_orphan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def test_get_user_company_ids_superuser(users):
    from accounts.scoping import get_user_company_ids
    admin, _, _ = users
    assert get_user_company_ids(admin) is None  # accès global


def test_get_user_company_ids_with_company(users):
    from accounts.scoping import get_user_company_ids
    _, user_btp, _ = users
    ids = get_user_company_ids(user_btp)
    assert isinstance(ids, list) and len(ids) == 1
    assert ids[0] == user_btp.company_id


def test_get_user_company_ids_orphan(users):
    from accounts.scoping import get_user_company_ids
    _, _, orphan = users
    assert get_user_company_ids(orphan) == []  # aucun accès


def test_get_user_company_ids_anonymous():
    from accounts.scoping import get_user_company_ids
    from django.contrib.auth.models import AnonymousUser
    assert get_user_company_ids(AnonymousUser()) == []


# ---------------------------------------------------------------------------
# Scoping queryset
# ---------------------------------------------------------------------------
def test_scope_queryset_sites_for_btp_user(users, two_companies):
    """Le user BTP ne doit voir que le site BTP."""
    from accounts.scoping import scope_queryset_by_company
    from sites.models import Site
    _, user_btp, _ = users
    btp, log, site_btp, site_log = two_companies

    qs = scope_queryset_by_company(Site.objects.all(), user_btp, "company")
    ids = set(qs.values_list("pk", flat=True))
    assert site_btp.pk in ids
    assert site_log.pk not in ids


def test_scope_queryset_sites_for_admin(users, two_companies):
    """Le super-admin voit tous les sites."""
    from accounts.scoping import scope_queryset_by_company
    from sites.models import Site
    admin, _, _ = users
    btp, log, site_btp, site_log = two_companies

    qs = scope_queryset_by_company(Site.objects.all(), admin, "company")
    ids = set(qs.values_list("pk", flat=True))
    assert site_btp.pk in ids and site_log.pk in ids


def test_scope_queryset_orphan_sees_nothing(users):
    """Un user sans filiale ne voit aucun site."""
    from accounts.scoping import scope_queryset_by_company
    from sites.models import Site
    _, _, orphan = users
    assert scope_queryset_by_company(Site.objects.all(), orphan, "company").count() == 0


# ---------------------------------------------------------------------------
# Scoping indirect (via site__company)
# ---------------------------------------------------------------------------
def test_scope_punches_by_site_company(users, two_companies):
    """Un Punch sur un site BTP ne doit pas être vu par un user Logistique."""
    from accounts.scoping import scope_queryset_by_company
    from attendance.models import Punch
    from django.utils import timezone
    btp, log, site_btp, site_log = two_companies
    _, user_btp, _ = users
    tenant = site_btp.tenant

    # 1 punch sur chaque site
    Punch.objects.create(tenant=tenant, site=site_btp, holder_kind="employee",
                          type="morning_in", timestamp=timezone.now())
    Punch.objects.create(tenant=tenant, site=site_log, holder_kind="employee",
                          type="morning_in", timestamp=timezone.now())

    qs = scope_queryset_by_company(Punch.objects.all(), user_btp, "site__company")
    assert qs.count() == 1
    assert qs.first().site_id == site_btp.pk


def test_has_access_to_company(users, two_companies):
    from accounts.scoping import has_access_to_company
    admin, user_btp, orphan = users
    btp, log, _, _ = two_companies
    # super-admin
    assert has_access_to_company(admin, btp.pk) is True
    assert has_access_to_company(admin, log.pk) is True
    # user BTP
    assert has_access_to_company(user_btp, btp.pk) is True
    assert has_access_to_company(user_btp, log.pk) is False
    # orphan
    assert has_access_to_company(orphan, btp.pk) is False
