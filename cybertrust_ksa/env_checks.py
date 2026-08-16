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


def validate_operational_services(
    *, debug, testing, email_backend, async_enabled, redis_url, broker_url,
    payment_provider, payment_mode, payment_secret, webhook_secret, mfa_encryption_key,
):
    """Reject incomplete production service configuration at startup."""
    if debug or testing:
        return
    if not mfa_encryption_key:
        raise ImproperlyConfigured(
            'MFA_ENCRYPTION_KEY must be set in production; keep it independent from DJANGO_SECRET_KEY.'
        )
    if email_backend == 'django.core.mail.backends.console.EmailBackend':
        raise ImproperlyConfigured(
            'EMAIL_BACKEND must be a real delivery backend when DEBUG=False; '
            'console email is not valid for production account verification.'
        )
    if async_enabled and (not redis_url or not broker_url):
        raise ImproperlyConfigured(
            'REDIS_URL and CELERY_BROKER_URL must be configured when EVIDENCE_ASYNC_ENABLED=True.'
        )
    if payment_provider == 'moyasar' and payment_mode == 'live':
        if not payment_secret or not webhook_secret:
            raise ImproperlyConfigured(
                'MOYASAR_SECRET_KEY and MOYASAR_WEBHOOK_SECRET are required for live payments.'
            )
