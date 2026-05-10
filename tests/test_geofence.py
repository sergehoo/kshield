"""Tests du service geofence + règle antifraud OUTSIDE_GEOFENCE."""
import pytest
from django.utils import timezone


# Polygone simple autour d'Abidjan (carré d'environ 200m x 200m)
ABIDJAN_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [-4.030, 5.340],
        [-4.020, 5.340],
        [-4.020, 5.350],
        [-4.030, 5.350],
        [-4.030, 5.340],
    ]],
}


@pytest.mark.integration
def test_site_contains_point_inside(db, kaydan_tenant, kaydan_company):
    from sites.geofence import site_contains_point
    from sites.models import Site
    s = Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="geo-1", name="Geofenced", type="construction",
        status="active", timezone="Africa/Abidjan",
        latitude=5.345, longitude=-4.025,
        geofence=ABIDJAN_POLYGON,
    )
    # point au centre
    assert site_contains_point(s, 5.345, -4.025) is True


@pytest.mark.integration
def test_site_contains_point_outside(db, kaydan_tenant, kaydan_company):
    from sites.geofence import site_contains_point
    from sites.models import Site
    s = Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="geo-2", name="Geofenced 2", type="office",
        status="active", timezone="Africa/Abidjan",
        latitude=5.345, longitude=-4.025,
        geofence=ABIDJAN_POLYGON,
    )
    # ~1 km plus au sud
    assert site_contains_point(s, 5.300, -4.025) is False


@pytest.mark.integration
def test_site_contains_point_no_geofence(db, site_chantier):
    """Sans polygone configuré, on retourne None (pas d'alerte)."""
    from sites.geofence import site_contains_point
    site_chantier.geofence = {}
    site_chantier.save()
    assert site_contains_point(site_chantier, 5.0, -4.0) is None


@pytest.mark.integration
def test_outside_geofence_rule_triggers(db, kaydan_tenant, kaydan_company):
    """La règle OUTSIDE_GEOFENCE crée une alerte si le scan est hors polygone."""
    from access_control.models import AccessEvent
    from antifraud.models import FraudRule
    from antifraud.services import evaluate
    from sites.models import Site
    s = Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="geo-3", name="Sec", type="warehouse",
        status="active", timezone="Africa/Abidjan",
        latitude=5.345, longitude=-4.025,
        geofence=ABIDJAN_POLYGON,
    )
    FraudRule.objects.create(
        tenant=kaydan_tenant, code="OUTSIDE_GEOFENCE",
        name="Hors zone", severity="high", is_active=True, parameters={},
    )
    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=s,
        timestamp=timezone.now(), badge_uid="GEO-1",
        latitude=5.300, longitude=-4.025,  # hors polygone
        decision="granted", method="nfc",
    )
    alerts = evaluate(ev)
    assert len(alerts) == 1
    assert alerts[0].rule.code == "OUTSIDE_GEOFENCE"


@pytest.mark.integration
def test_outside_geofence_rule_silent_when_inside(db, kaydan_tenant, kaydan_company):
    from access_control.models import AccessEvent
    from antifraud.models import FraudAlert, FraudRule
    from antifraud.services import evaluate
    from sites.models import Site
    s = Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="geo-4", name="Sec2", type="warehouse",
        status="active", timezone="Africa/Abidjan",
        latitude=5.345, longitude=-4.025,
        geofence=ABIDJAN_POLYGON,
    )
    FraudRule.objects.create(
        tenant=kaydan_tenant, code="OUTSIDE_GEOFENCE",
        name="Hors zone", severity="high", is_active=True, parameters={},
    )
    ev = AccessEvent.objects.create(
        tenant=kaydan_tenant, site=s,
        timestamp=timezone.now(), badge_uid="GEO-2",
        latitude=5.345, longitude=-4.025,  # bien dedans
        decision="granted", method="nfc",
    )
    evaluate(ev)
    assert FraudAlert.objects.count() == 0


@pytest.mark.integration
def test_closest_site_haversine(db, kaydan_tenant, kaydan_company):
    """closest_site renvoie le site le plus proche par distance haversine."""
    from sites.geofence import closest_site
    from sites.models import Site
    Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="A", name="A", type="office",
        status="active", timezone="Africa/Abidjan",
        latitude=5.300, longitude=-4.000,
    )
    s_close = Site.objects.create(
        tenant=kaydan_tenant, company=kaydan_company,
        code="B", name="B", type="office",
        status="active", timezone="Africa/Abidjan",
        latitude=5.345, longitude=-4.025,
    )
    result = closest_site(Site.objects.all(), 5.346, -4.024)
    assert result.id == s_close.id
