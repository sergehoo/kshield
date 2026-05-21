"""KAYDAN SHIELD — Tests du module streaming (caméras IP).

Couverture :
  1. Helpers Redis (channel/alive key names)
  2. `is_worker_alive` retourne False si Redis indispo
  3. `stream_camera` choisit Redis vs direct selon `is_worker_alive`
  4. `_wrap_frame` formate correctement le multipart MJPEG
  5. `EncryptedCharField` round-trip (chiffrement Camera.password)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Helpers Redis (constantes nommage)
# ---------------------------------------------------------------------------
def test_camera_channel_name():
    from devices.streaming import camera_channel
    assert camera_channel(42) == "camera:42:frames"


def test_camera_alive_key_name():
    from devices.streaming import camera_alive_key
    assert camera_alive_key(42) == "camera:42:alive"


# ---------------------------------------------------------------------------
# 2. is_worker_alive — gracieux si Redis indispo
# ---------------------------------------------------------------------------
def test_is_worker_alive_returns_false_when_redis_missing():
    from devices.streaming import is_worker_alive
    with patch("devices.streaming._get_redis", return_value=None):
        assert is_worker_alive(1) is False


def test_is_worker_alive_returns_false_on_redis_exception():
    from devices.streaming import is_worker_alive
    fake = MagicMock()
    fake.exists.side_effect = ConnectionError("Redis down")
    with patch("devices.streaming._get_redis", return_value=fake):
        assert is_worker_alive(1) is False


def test_is_worker_alive_true_when_key_exists():
    from devices.streaming import is_worker_alive
    fake = MagicMock()
    fake.exists.return_value = 1
    with patch("devices.streaming._get_redis", return_value=fake):
        assert is_worker_alive(1) is True


# ---------------------------------------------------------------------------
# 3. _wrap_frame — format multipart correct
# ---------------------------------------------------------------------------
def test_wrap_frame_includes_boundary_and_length():
    from devices.streaming import _wrap_frame
    jpeg = b"\xff\xd8\xff\xd9"  # JPEG start/end markers
    chunk = _wrap_frame(jpeg)
    assert chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 4")
    assert chunk.endswith(b"\r\n")
    assert jpeg in chunk


# ---------------------------------------------------------------------------
# 4. stream_camera fallback : sans worker → direct
# ---------------------------------------------------------------------------
def test_stream_camera_uses_direct_when_no_worker():
    """Si is_worker_alive=False, stream_camera doit appeler stream_camera_direct."""
    from devices.streaming import stream_camera

    mock_camera = MagicMock(pk=1)
    with patch("devices.streaming.is_worker_alive", return_value=False), \
         patch("devices.streaming.stream_camera_direct") as direct, \
         patch("devices.streaming.stream_camera_from_redis") as redis:
        direct.return_value = iter([b"frame1", b"frame2"])
        list(stream_camera(mock_camera, max_seconds=1))
        direct.assert_called_once()
        redis.assert_not_called()


def test_stream_camera_uses_redis_when_worker_alive():
    """Si is_worker_alive=True, stream_camera doit appeler stream_camera_from_redis."""
    from devices.streaming import stream_camera

    mock_camera = MagicMock(pk=1)
    with patch("devices.streaming.is_worker_alive", return_value=True), \
         patch("devices.streaming.stream_camera_direct") as direct, \
         patch("devices.streaming.stream_camera_from_redis") as redis:
        redis.return_value = iter([b"frame1"])
        list(stream_camera(mock_camera, max_seconds=1))
        redis.assert_called_once()
        direct.assert_not_called()


def test_stream_camera_falls_back_to_direct_on_redis_crash():
    """Si Redis stream crashe en cours, on retombe sur direct."""
    from devices.streaming import stream_camera

    mock_camera = MagicMock(pk=1)

    def fail_redis(*args, **kwargs):
        raise ConnectionError("Redis down")

    with patch("devices.streaming.is_worker_alive", return_value=True), \
         patch("devices.streaming.stream_camera_direct") as direct, \
         patch("devices.streaming.stream_camera_from_redis",
                 side_effect=fail_redis) as redis:
        direct.return_value = iter([b"frame1"])
        list(stream_camera(mock_camera, max_seconds=1))
        redis.assert_called_once()
        direct.assert_called_once()  # fallback déclenché


# ---------------------------------------------------------------------------
# 5. EncryptedCharField round-trip
# ---------------------------------------------------------------------------
def test_encrypted_field_round_trip():
    """Le champ chiffre à l'écriture et déchiffre à la lecture."""
    from core.fields import EncryptedCharField, _get_fernet
    field = EncryptedCharField()
    plain = "ma-secret-password-RTSP-123!"

    # get_prep_value → chiffre
    cipher = field.get_prep_value(plain)
    assert cipher != plain
    assert len(cipher) > len(plain)  # overhead Fernet

    # from_db_value → déchiffre
    decrypted = field.from_db_value(cipher, None, None)
    assert decrypted == plain


def test_encrypted_field_passthrough_on_legacy_plaintext():
    """Un legacy plaintext (non chiffré) est retourné tel quel."""
    from core.fields import EncryptedCharField
    field = EncryptedCharField()
    legacy = "old_plaintext_password"
    assert field.from_db_value(legacy, None, None) == legacy


def test_encrypted_field_handles_empty_value():
    """Empty/None reste empty/None — pas de tentative de chiffrement."""
    from core.fields import EncryptedCharField
    field = EncryptedCharField()
    assert field.get_prep_value("") == ""
    assert field.get_prep_value(None) is None
    assert field.from_db_value("", None, None) == ""
    assert field.from_db_value(None, None, None) is None


def test_encrypted_field_ciphertext_is_not_predictable():
    """Deux chiffrements du même plaintext donnent des cipher différents (Fernet utilise un IV)."""
    from core.fields import EncryptedCharField
    field = EncryptedCharField()
    c1 = field.get_prep_value("hello")
    c2 = field.get_prep_value("hello")
    assert c1 != c2  # Fernet aléatoire
    # Mais les deux déchiffrent au même plaintext
    assert field.from_db_value(c1, None, None) == "hello"
    assert field.from_db_value(c2, None, None) == "hello"
