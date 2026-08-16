"""Encryption for MFA secrets with an independently rotatable Fernet key."""
from __future__ import annotations

import base64
import hashlib

from django.conf import settings

_PREFIX = 'enc:'


def _legacy_derived_key() -> str:
    """Compatibility key for ciphertext produced before MFA_ENCRYPTION_KEY existed."""
    return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()


def _key_material() -> tuple[str, ...]:
    """Return primary then fallbacks; development retains a deterministic compatibility key."""
    primary = (getattr(settings, 'MFA_ENCRYPTION_KEY', '') or '').strip()
    previous = tuple(getattr(settings, 'MFA_PREVIOUS_ENCRYPTION_KEYS', ()) or ())
    if primary:
        return (primary, *previous, _legacy_derived_key())
    return (_legacy_derived_key(),)


def _fernet(key: str):
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def encrypt_secret(plain):
    """Encrypt a non-empty MFA secret using the configured primary key."""
    if not plain:
        return plain
    return _PREFIX + _fernet(_key_material()[0]).encrypt(plain.encode()).decode()


def decrypt_secret(value):
    """Decrypt current/previous ciphertext; preserve legacy plaintext for controlled migration."""
    if not value:
        return value
    if not value.startswith(_PREFIX):
        return value
    from cryptography.fernet import InvalidToken

    ciphertext = value[len(_PREFIX):].encode()
    for key in _key_material():
        try:
            return _fernet(key).decrypt(ciphertext).decode()
        except (InvalidToken, ValueError, TypeError):
            continue
    return ''
