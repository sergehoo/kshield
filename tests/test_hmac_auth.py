"""Tests de l'authentification HMAC pour les terminaux IoT."""
import hashlib
import json
import time

import pytest
from django.test import Client

from accounts.hmac_auth import sign


@pytest.fixture
def api_key(db, kaydan_tenant):
    """Crée une APIKey active dont le secret_hash est connu pour signer."""
    from accounts.models import APIKey
    raw_secret = "test-secret-1234567890"
    secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()
    return APIKey.objects.create(
        tenant=kaydan_tenant,
        name="Test gateway",
        scope="device_terminal",
        public_id="ktest1234567890",
        secret_hash=secret_hash,
        is_active=True,
    )


@pytest.mark.integration
def test_hmac_canonical_string_stable():
    from accounts.hmac_auth import canonical_string
    s = canonical_string("1700000000", "POST", "/api/v1/access/scan/", b'{"x":1}')
    parts = s.split("\n")
    assert parts[0] == "1700000000"
    assert parts[1] == "POST"
    assert parts[2] == "/api/v1/access/scan/"
    assert len(parts[3]) == 64  # sha256 hex


@pytest.mark.integration
def test_hmac_sign_deterministic():
    a = sign("hashedsecret", "1700000000", "POST", "/x/", b'{"a":1}')
    b = sign("hashedsecret", "1700000000", "POST", "/x/", b'{"a":1}')
    assert a == b
    # changement du body change la sig
    assert sign("hashedsecret", "1700000000", "POST", "/x/", b'{"a":2}') != a


@pytest.mark.integration
def test_scan_endpoint_rejects_unauthenticated(db):
    c = Client()
    r = c.post("/api/v1/access/scan/", data="{}", content_type="application/json")
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.content[:100]}"


@pytest.mark.integration
def test_scan_endpoint_accepts_valid_hmac(db, api_key, site_chantier, device):
    c = Client()
    body = json.dumps({
        "device_id": str(device.id),
        "method": "nfc",
        "badge_uid": "TEST-UID-001",
        "site_id": site_chantier.id,
    }).encode()
    ts = str(int(time.time()))
    sig = sign(api_key.secret_hash, ts, "POST", "/api/v1/access/scan/", body)
    r = c.post(
        "/api/v1/access/scan/",
        data=body, content_type="application/json",
        HTTP_X_KSHIELD_KEY_ID=api_key.public_id,
        HTTP_X_KSHIELD_TIMESTAMP=ts,
        HTTP_X_KSHIELD_SIGNATURE=sig,
    )
    assert r.status_code in (201, 400), f"unexpected {r.status_code}: {r.content[:200]}"
    # 400 si le serializer recale la payload — l'auth a marché.


@pytest.mark.integration
def test_scan_endpoint_rejects_bad_signature(db, api_key):
    c = Client()
    body = b'{"device_id":1}'
    ts = str(int(time.time()))
    bad_sig = "0" * 64
    r = c.post(
        "/api/v1/access/scan/", data=body, content_type="application/json",
        HTTP_X_KSHIELD_KEY_ID=api_key.public_id,
        HTTP_X_KSHIELD_TIMESTAMP=ts,
        HTTP_X_KSHIELD_SIGNATURE=bad_sig,
    )
    assert r.status_code == 401


@pytest.mark.integration
def test_scan_endpoint_rejects_clock_skew(db, api_key):
    c = Client()
    body = b'{}'
    old_ts = str(int(time.time()) - 5_000)  # 83 min in past
    sig = sign(api_key.secret_hash, old_ts, "POST", "/api/v1/access/scan/", body)
    r = c.post(
        "/api/v1/access/scan/", data=body, content_type="application/json",
        HTTP_X_KSHIELD_KEY_ID=api_key.public_id,
        HTTP_X_KSHIELD_TIMESTAMP=old_ts,
        HTTP_X_KSHIELD_SIGNATURE=sig,
    )
    assert r.status_code == 401


@pytest.mark.integration
def test_scan_endpoint_rejects_revoked_key(db, api_key):
    from django.utils import timezone
    api_key.is_active = False
    api_key.revoked_at = timezone.now()
    api_key.save()

    c = Client()
    body = b'{}'
    ts = str(int(time.time()))
    sig = sign(api_key.secret_hash, ts, "POST", "/api/v1/access/scan/", body)
    r = c.post(
        "/api/v1/access/scan/", data=body, content_type="application/json",
        HTTP_X_KSHIELD_KEY_ID=api_key.public_id,
        HTTP_X_KSHIELD_TIMESTAMP=ts,
        HTTP_X_KSHIELD_SIGNATURE=sig,
    )
    assert r.status_code == 401
