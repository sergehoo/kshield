import pytest


@pytest.fixture
def enrollment_company_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="rfid-enrollment@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.fixture
def enrollment_scan_user(db, kaydan_company):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        email="rfid-scan@kaydan.test",
        password="x",
        company=kaydan_company,
        tenant=None,
    )


@pytest.mark.django_db
def test_rfid_enrollment_uses_company_tenant_for_full_session(
    api_client, enrollment_company_user, kaydan_tenant
):
    from devices.models import Badge, RFIDEnrollmentSession

    api_client.force_authenticate(enrollment_company_user)

    started = api_client.post(
        "/api/v1/rfid/enrollment/start/",
        {"mode": "single", "timeout_seconds": 180},
        format="json",
    )

    assert started.status_code == 201
    session_id = started.json()["id"]
    session = RFIDEnrollmentSession.objects.get(uuid=session_id)
    assert session.tenant_id == kaydan_tenant.pk
    assert session.initiated_by_id == enrollment_company_user.pk
    assert started.json()["channel_group"] == f"enrollment.{session_id}"

    detail = api_client.get(
        f"/api/v1/rfid/enrollment/sessions/{session_id}/"
    )
    assert detail.status_code == 200

    ingested = api_client.post(
        "/api/v1/rfid/enrollment/ingest/",
        {
            "session_id": session_id,
            "uid": "RFID-ENROLLMENT-API-001",
        },
        format="json",
    )
    assert ingested.status_code == 201
    assert ingested.json()["session_id"] == session_id

    confirmed = api_client.post(
        f"/api/v1/rfid/enrollment/{session_id}/confirm/",
        {
            "uid": "RFID-ENROLLMENT-API-001",
            "tech": "uhf",
            "category": "worker_rfid",
        },
        format="json",
    )
    assert confirmed.status_code == 201
    badge = Badge.objects.get(pk=confirmed.json()["badge_id"])
    assert badge.tenant_id == kaydan_tenant.pk

    stopped = api_client.post(
        f"/api/v1/rfid/enrollment/{session_id}/stop/",
        {"reason": "test"},
        format="json",
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"


@pytest.mark.django_db
def test_scan_inbox_forwards_scan_to_active_enrollment_session(
    api_client, enrollment_scan_user, kaydan_tenant, device
):
    from devices.models import RFIDEnrollmentEvent, RFIDEnrollmentSession

    session = RFIDEnrollmentSession.objects.create(
        tenant=kaydan_tenant,
        initiated_by=enrollment_scan_user,
        status="listening",
        mode="single",
    )
    api_client.force_authenticate(enrollment_scan_user)

    response = api_client.post(
        "/api/v1/devices/scan/inbox/",
        {
            "reader_id": device.pk,
            "uid": "live-scan-001",
            "rssi": -42,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["enrollment"]["session_id"] == str(session.uuid)
    event = RFIDEnrollmentEvent.objects.get(session=session)
    assert event.uid == "LIVE-SCAN-001"
    assert event.device_id == device.pk
    assert event.rssi == -42
