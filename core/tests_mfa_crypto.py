"""DD P1 — the TOTP secret is encrypted at rest, with backward compatibility for any
pre-existing plaintext secret. Verifying a code must still work through the encrypted path.
"""
from django.test import TestCase

from core.crypto import encrypt_secret, decrypt_secret, _PREFIX
from core.models import User
from core.services import verify_totp


class MfaSecretCryptoTests(TestCase):
    def test_encrypt_roundtrip(self):
        plain = 'JBSWY3DPEHPK3PXP'
        token = encrypt_secret(plain)
        self.assertTrue(token.startswith(_PREFIX))
        self.assertNotIn(plain, token)              # ciphertext does not leak the secret
        self.assertEqual(decrypt_secret(token), plain)

    def test_legacy_plaintext_passthrough(self):
        # A value stored before encryption existed (no prefix) is returned unchanged.
        self.assertEqual(decrypt_secret('JBSWY3DPEHPK3PXP'), 'JBSWY3DPEHPK3PXP')

    def test_empty_values(self):
        self.assertEqual(encrypt_secret(''), '')
        self.assertEqual(decrypt_secret(''), '')

    def test_model_stores_ciphertext_but_reads_plaintext(self):
        u = User.objects.create_user(email='mfa@x.com', password='longenough12',
                                     first_name='A', last_name='B')
        u.set_mfa_secret('JBSWY3DPEHPK3PXP')
        u.save(update_fields=['mfa_secret'])
        u.refresh_from_db()
        self.assertTrue(u.mfa_secret.startswith(_PREFIX))     # stored encrypted
        self.assertEqual(u.get_mfa_secret(), 'JBSWY3DPEHPK3PXP')  # read decrypted

    def test_verify_totp_works_through_encrypted_secret(self):
        import pyotp
        secret = pyotp.random_base32()
        u = User.objects.create_user(email='mfa2@x.com', password='longenough12',
                                     first_name='A', last_name='B')
        u.set_mfa_secret(secret)
        u.save(update_fields=['mfa_secret'])
        code = pyotp.TOTP(secret).now()
        self.assertTrue(verify_totp(u, code))
        self.assertFalse(verify_totp(u, '000000'))

    def test_verify_totp_still_works_for_legacy_plaintext_secret(self):
        import pyotp
        secret = pyotp.random_base32()
        u = User.objects.create_user(email='mfa3@x.com', password='longenough12',
                                     first_name='A', last_name='B')
        # Simulate a pre-encryption row: raw plaintext in the column.
        User.objects.filter(pk=u.pk).update(mfa_secret=secret)
        u.refresh_from_db()
        self.assertTrue(verify_totp(u, pyotp.TOTP(secret).now()))
