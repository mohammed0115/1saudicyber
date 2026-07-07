"""P0-1 / P0-2: fail-closed environment validation."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from cybertrust_ksa.env_checks import (
    DEFAULT_SECRET_KEY, validate_secret_key, validate_allowed_hosts)


class SecretKeyValidationTests(SimpleTestCase):
    def test_prod_missing_key_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_secret_key('', debug=False, testing=False)

    def test_prod_default_key_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_secret_key(DEFAULT_SECRET_KEY, debug=False, testing=False)

    def test_prod_real_key_boots(self):
        validate_secret_key('a-strong-random-secret-value', debug=False, testing=False)  # no raise

    def test_debug_allows_default_key(self):
        validate_secret_key(DEFAULT_SECRET_KEY, debug=True, testing=False)  # no raise

    def test_testrunner_allows_default_key(self):
        validate_secret_key(DEFAULT_SECRET_KEY, debug=False, testing=True)  # no raise


class AllowedHostsValidationTests(SimpleTestCase):
    def test_prod_empty_hosts_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_allowed_hosts([], debug=False, testing=False)

    def test_prod_wildcard_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_allowed_hosts(['*'], debug=False, testing=False)

    def test_prod_explicit_host_boots(self):
        validate_allowed_hosts(['app.example.sa'], debug=False, testing=False)  # no raise

    def test_debug_allows_empty_hosts(self):
        validate_allowed_hosts([], debug=True, testing=False)  # no raise

    def test_testrunner_allows_empty_hosts(self):
        validate_allowed_hosts([], debug=False, testing=True)  # no raise
