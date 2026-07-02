"""Phase 8I-B — Moyasar sandbox checkout helpers (config only; no API calls).

SECURITY:
* The SECRET key is NEVER read here for template use and never returned to callers
  that render HTML. Only the PUBLISHABLE key (and only a safe sandbox pk_test_ one)
  is exposed to the browser.
* No card data is handled by our backend. This module builds config + metadata only.
* This phase does NOT call the Moyasar API and does NOT verify payments.
"""
from django.conf import settings

MOYASAR_JS = 'https://cdn.moyasar.com/mpf/1.7.3/moyasar.js'
MOYASAR_CSS = 'https://cdn.moyasar.com/mpf/1.7.3/moyasar.css'


def payment_provider():
    return (getattr(settings, 'PAYMENT_PROVIDER', 'manual') or 'manual').lower()


def is_moyasar_provider():
    return payment_provider() == 'moyasar'


def moyasar_mode():
    return (getattr(settings, 'MOYASAR_MODE', 'sandbox') or 'sandbox').lower()


def publishable_key_for_template():
    """Return the publishable key ONLY when it is a safe sandbox key (pk_test_...).

    Anything else (empty, or a live pk_live_ key) returns '' so no live key ever
    reaches the browser in this sandbox-only phase.
    """
    key = (getattr(settings, 'MOYASAR_PUBLISHABLE_KEY', '') or '').strip()
    if key.startswith('pk_test_'):
        return key
    return ''


def is_configured():
    """True only when a safe sandbox publishable key is present."""
    return bool(publishable_key_for_template())


def build_callback_url(request, payment):
    """Absolute callback URL carrying our internal payment id (tenant-checked later)."""
    from django.urls import reverse
    path = reverse('billing:moyasar_callback')
    base = (getattr(settings, 'PUBLIC_BASE_URL', '') or '').rstrip('/')
    rel = '%s?ipid=%s' % (path, payment.id)
    if base:
        return base + rel
    try:
        return request.build_absolute_uri(rel)
    except Exception:
        return rel


def checkout_metadata(payment):
    """Non-sensitive metadata sent to Moyasar (no secrets, no CRM notes, no card data)."""
    sub = payment.subscription
    return {
        'internal_payment_id': str(payment.id),
        'company_id': str(payment.company_id),
        'subscription_id': str(payment.subscription_id or ''),
        'plan_code': (sub.plan.code if sub and sub.plan_id else ''),
    }
