"""Signature HMAC-SHA256 des messages agent → serveur (anti-rejeu)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


def sign_payload(secret: str, payload: dict[str, Any], ts: int | None = None) -> tuple[str, str]:
    """Retourne ``(timestamp, signature)`` pour un payload JSON.

    Le serveur vérifie : ``hmac_sha256(secret, f"{ts}.{body}")`` avec ``ts`` <5min.
    """
    ts = ts or int(time.time())
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    msg = f"{ts}.{body}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return str(ts), sig


def verify_signature(secret: str, ts: str, body: bytes, provided_sig: str,
                      max_age_seconds: int = 300) -> bool:
    """Vérifie une signature reçue côté serveur.

    Refuse les messages trop anciens (anti-rejeu).
    """
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > max_age_seconds:
        return False
    msg = f"{ts}.{body.decode()}".encode()
    expected = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided_sig)
