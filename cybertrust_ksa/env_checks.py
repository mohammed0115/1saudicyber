"""Startup environment validation (fail-closed for production).

Kept as small pure functions so they can be unit-tested without re-importing the
whole settings module. Called from settings.py at import time.
"""
from django.core.exceptions import ImproperlyConfigured

# The insecure development fallback. Production (DEBUG=False) must override it.
DEFAULT_SECRET_KEY = 'dev-secret-key-change-in-production'


def validate_secret_key(secret_key, debug, testing=False):
    """Fail-closed: in production the secret key must be set and non-default.

    No-op in DEBUG or under the test runner so local dev / CI keep working.
    """
    if debug or testing:
        return
    if not secret_key or secret_key == DEFAULT_SECRET_KEY:
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY must be set to a strong, non-default value when DEBUG=False. '
            'Set the DJANGO_SECRET_KEY environment variable.'
        )


def validate_allowed_hosts(allowed_hosts, debug, testing=False):
    """Fail-closed: production must list explicit hostnames (no empty, no wildcard '*').

    No-op in DEBUG or under the test runner.
    """
    if debug or testing:
        return
    explicit = [h for h in (allowed_hosts or []) if h and h != '*']
    if not explicit:
        raise ImproperlyConfigured(
            'ALLOWED_HOSTS must list explicit hostnames when DEBUG=False (no empty value, no "*"). '
            'Set the ALLOWED_HOSTS environment variable, e.g. "app.example.sa,www.example.sa".'
        )
