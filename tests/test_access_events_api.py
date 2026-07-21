from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


@pytest.fixture
def access_events_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        email="access-events-api@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.mark.django_db
def test_access_event_list_and_detail_expose_operator_context(
    api_client,
    access_events_user,
    kaydan_tenant,
    site_chantier,
    employee,
    device,
):
    from access_control.models import AccessDecision, AccessEvent, DoorCommand
    from sites.models import Checkpoint, Zone

    zone = Zone.objects.create(
        site=site_chantier,
        name="Hall principal",
        code="hall-principal",
        is_restricted=True,
    )
    checkpoint = Checkpoint.objects.create(
        site=site_chantier,
        zone=zone,
        name="Portique nord",
        code="portique-nord",
        type="entry",
        mode="fixed",
        method="nfc",
    )
    scanned_at = timezone.now() - timedelta(milliseconds=125)
    event = AccessEvent.objects.create(
        timestamp=scanned_at,
        tenant=kaydan_tenant,
        site=site_chantier,
        zone=zone,
        checkpoint=checkpoint,
        device=device,
        badge_uid="EMP-04F7-3A21",
        holder_kind="employee",
        holder_content_type=ContentType.objects.get_for_model(employee),
        holder_object_id=employee.pk,
        direction="in",
        method="nfc",
        decision="denied",
        denial_reason="Accès hors plage autorisée",
        raw_payload={"source": "reader"},
    )
    AccessDecision.objects.create(
        event=event,
        rules_evaluated=[{"code": "TIME-WINDOW", "matched": True}],
        deciding_rule_code="TIME-WINDOW",
        risk_score=0.72,
        notes="Contrôle horaire déclenché",
    )
    DoorCommand.objects.create(
        checkpoint=checkpoint,
        device=device,
        related_event=event,
        command="lock",
        status="succeeded",
        latency_ms=48,
    )
    api_client.force_authenticate(access_events_user)

    list_response = api_client.get("/api/v1/access/events/")

    assert list_response.status_code == 200
    listed = list_response.json()["results"][0]
    assert listed["holder_name"] == "Aïcha Bamba"
    assert listed["holder_detail"]["reference"] == "EMP-TEST-001"
    assert listed["device_detail"]["serial_number"] == "DEV-TEST-001"
    assert listed["site_detail"]["name"] == "Chantier Test"
    assert listed["zone_detail"]["name"] == "Hall principal"
    assert listed["checkpoint_detail"]["name"] == "Portique nord"
    assert listed["decision_label"] == "Refusé"
    assert listed["method_label"] == "NFC"
    assert listed["processing_delay_ms"] >= 0
    assert "decision_trace" not in listed
    assert "door_commands" not in listed

    detail_response = api_client.get(f"/api/v1/access/events/{event.pk}/")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["denial_reason"] == "Accès hors plage autorisée"
    assert detail["decision_trace"]["deciding_rule_code"] == "TIME-WINDOW"
    assert detail["decision_trace"]["risk_score"] == 0.72
    assert detail["door_commands"][0]["command_label"] == "Verrouiller"
    assert detail["door_commands"][0]["status_label"] == "Succès"
