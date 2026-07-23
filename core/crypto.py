"""Symmetric encryption for secrets at rest (DD P1 — MFA secret was stored in plaintext).

A single Fernet key is derived from ``settings.SECRET_KEY`` so no new key material has to
be provisioned. Values are stored with an ``enc:`` prefix; anything without the prefix is
treated as legacy plaintext and passed through unchanged, so pre-existing TOTP secrets keep
working and get upgraded to ciphertext the next time they are written.

If SECRET_KEY is rotated, old ciphertext becomes undecryptable; decrypt_secret returns ''
in that case (forcing a clean MFA re-enrolment) rather than raising.
"""
import base64
import hashlib

from django.conf import settings

_PREFIX = 'enc:'


def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain):
    """Encrypt a plaintext secret. Empty/None passes through unchanged."""
    if not plain:
        return plain
    return _PREFIX + _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(value):
    """Decrypt a stored value. Legacy plaintext (no prefix) is returned as-is;
    undecryptable ciphertext returns '' rather than raising."""
    if not value:
        return value
    if not value.startswith(_PREFIX):
        return value  # legacy plaintext — backward compatible
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return ''
