"""KAYDAN SHIELD — Champs Django custom (chiffrement, etc).

EncryptedCharField/TextField : chiffrement Fernet (AES-128-CBC + HMAC-SHA256)
au repos pour les secrets stockés en DB (mots de passe RTSP caméras, tokens
OAuth, etc).

Utilisation :
    from core.fields import EncryptedCharField

    class Camera(models.Model):
        password = EncryptedCharField(max_length=255, blank=True)

Configuration :
    settings.FIELD_ENCRYPTION_KEY  # Fernet key, base64-urlsafe 32 bytes
    Si absente → dérivée de SECRET_KEY via SHA-256 (fallback acceptable
    en dev, MAIS PAS EN PROD — générer une vraie clé avec :
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    puis l'ajouter à .env : FIELD_ENCRYPTION_KEY=<la-clé>

Rétrocompatibilité : les valeurs en clair (anciennes ou si le ciphertext est
corrompu) sont retournées telles quelles → migration progressive sans casser
les DB existantes. Sauvegarde force le ré-chiffrement.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fernet helper — singleton lazy
# ---------------------------------------------------------------------------
_fernet_instance = None


def _get_fernet():
    """Retourne un Fernet ou None si cryptography est manquant."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography manquant — EncryptedField fonctionne en clair !")
        return None

    key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
    if not key:
        # Fallback : dérive depuis SECRET_KEY (compat dev, pas idéal en prod)
        secret = getattr(settings, "SECRET_KEY", "kaydan-default-key-change-me")
        derived = hashlib.sha256(secret.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(derived)
        logger.warning(
            "FIELD_ENCRYPTION_KEY absente — clé dérivée de SECRET_KEY (NON RECOMMANDÉ en prod). "
            "Générer une vraie clé : python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    if isinstance(key, str):
        key = key.encode("utf-8")
    try:
        _fernet_instance = Fernet(key)
    except Exception as exc:
        logger.error("Fernet init échouée : %s — chiffrement désactivé.", exc)
        _fernet_instance = None
    return _fernet_instance


# ---------------------------------------------------------------------------
# Mixin commun (chiffre/déchiffre transparent)
# ---------------------------------------------------------------------------
class _EncryptedFieldMixin:
    """Mixin : auto-encrypt en DB / auto-decrypt à la lecture.

    Tolère les valeurs déjà en clair (legacy) — retourne tel quel si le
    déchiffrement échoue. Permet une migration progressive sans data loss.
    """

    def from_db_value(self, value: Optional[str], expression, connection):
        if value is None or value == "":
            return value
        f = _get_fernet()
        if f is None:
            return value  # crypto indispo, on retourne tel quel
        try:
            return f.decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            # Legacy plaintext ou ciphertext corrompu — passthrough
            return value

    def to_python(self, value):
        # Cas où l'attribut est assigné côté Python sans passer par DB
        return value

    def get_prep_value(self, value: Optional[str]):
        if value is None or value == "":
            return value
        f = _get_fernet()
        if f is None:
            return value
        try:
            return f.encrypt(str(value).encode("utf-8")).decode("utf-8")
        except Exception as exc:
            logger.error("Échec encryption (%s) — value stockée en clair.", exc)
            return value


# ---------------------------------------------------------------------------
# Champs publics
# ---------------------------------------------------------------------------
class EncryptedCharField(_EncryptedFieldMixin, models.CharField):
    """CharField auto-chiffré au repos via Fernet.

    Note : la taille max_length doit prendre en compte l'overhead Fernet
    (~100 octets de plus que le plaintext). Pour un password de 64 chars,
    prévoir max_length=255 minimum.
    """


class EncryptedTextField(_EncryptedFieldMixin, models.TextField):
    """TextField auto-chiffré (pour tokens OAuth longs, JWT, etc)."""
