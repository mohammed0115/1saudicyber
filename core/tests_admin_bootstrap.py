"""P0-5: initial superuser comes from env only — no hardcoded credentials."""
from django.test import TestCase

from core.models import User
from core.admin_bootstrap import create_superuser_from_env, AdminCredentialsMissing


class AdminBootstrapTests(TestCase):
    def test_missing_both_refuses(self):
        with self.assertRaises(AdminCredentialsMissing):
            create_superuser_from_env({}, User)

    def test_missing_password_refuses(self):
        with self.assertRaises(AdminCredentialsMissing):
            create_superuser_from_env({'ADMIN_EMAIL': 'a@x.com'}, User)

    def test_creates_superuser_from_env(self):
        created, email = create_superuser_from_env(
            {'ADMIN_EMAIL': 'boss@x.com', 'ADMIN_PASSWORD': 'a-strong-pass-123'}, User)
        self.assertTrue(created)
        self.assertEqual(email, 'boss@x.com')
        u = User.objects.get(email='boss@x.com')
        self.assertTrue(u.is_superuser and u.is_staff)

    def test_idempotent_when_exists(self):
        env = {'ADMIN_EMAIL': 'boss2@x.com', 'ADMIN_PASSWORD': 'a-strong-pass-123'}
        create_superuser_from_env(env, User)
        created, _ = create_superuser_from_env(env, User)
        self.assertFalse(created)
        self.assertEqual(User.objects.filter(email='boss2@x.com').count(), 1)
