"""Phase 8I-B — Moyasar sandbox checkout helpers (config only; no API calls).

SECURITY:
* The SECRET key is NEVER read here for template use and never returned to callers
  that render HTML. Only the PUBLISHABLE key (and only a safe sandbox pk_test_ one)
  is exposed to the browser.
* No card data is handled by our backend. This module builds config + metadata only.
* This phase does NOT call the Moyasar API and does NOT verify payments.
"""
import base64
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

MOYASAR_JS = 'https://cdn.moyasar.com/mpf/1.7.3/moyasar.js'
MOYASAR_CSS = 'https://cdn.moyasar.com/mpf/1.7.3/moyasar.css'
MOYASAR_API_BASE = 'https://api.moyasar.com/v1'
FETCH_TIMEOUT = 15  # seconds


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


# ---------------------------------------------------------------------------
# Server-side secret (NEVER exposed to templates / browser / logs)
# ---------------------------------------------------------------------------
def secret_key():
    """The Moyasar SECRET key. Server-side only — never render this in a template."""
    return (getattr(settings, 'MOYASAR_SECRET_KEY', '') or '').strip()


def has_secret():
    return bool(secret_key())


def webhook_secret():
    """Optional shared token echoed by Moyasar dashboard webhooks (may be empty)."""
    return (getattr(settings, 'MOYASAR_WEBHOOK_SECRET', '') or '').strip()


def fetch_moyasar_payment(provider_payment_id, timeout=FETCH_TIMEOUT):
    """Server-side Fetch Payment (source of truth for activation). Never raises.

    Returns {'ok': bool, 'status_code': int, 'payload': dict, 'error': str}. Uses
    HTTP Basic auth with the SECRET key as the username (Moyasar convention). The
    secret is never logged. Any network/HTTP/parse error returns ok=False safely.
    """
    key = secret_key()
    if not key:
        return {'ok': False, 'status_code': 0, 'payload': {}, 'error': 'no_secret'}
    pid = str(provider_payment_id or '').strip()
    if not pid:
        return {'ok': False, 'status_code': 0, 'payload': {}, 'error': 'no_id'}
    url = '%s/payments/%s' % (MOYASAR_API_BASE, urllib.parse.quote(pid, safe=''))
    token = base64.b64encode(('%s:' % key).encode('utf-8')).decode('ascii')
    req = urllib.request.Request(url, headers={
        'Authorization': 'Basic %s' % token, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            data = json.loads(body or '{}')
            return {'ok': True, 'status_code': getattr(resp, 'status', 200),
                    'payload': data if isinstance(data, dict) else {}, 'error': ''}
    except urllib.error.HTTPError as e:
        return {'ok': False, 'status_code': getattr(e, 'code', 0), 'payload': {},
                'error': 'http_%s' % getattr(e, 'code', 'err')}
    except (urllib.error.URLError, socket.timeout, ValueError, OSError):
        return {'ok': False, 'status_code': 0, 'payload': {}, 'error': 'network'}
    except Exception:
        return {'ok': False, 'status_code': 0, 'payload': {}, 'error': 'unknown'}


def checkout_metadata(payment):
    """Non-sensitive metadata sent to Moyasar (no secrets, no CRM notes, no card data)."""
    sub = payment.subscription
    return {
        'internal_payment_id': str(payment.id),
        'company_id': str(payment.company_id),
        'subscription_id': str(payment.subscription_id or ''),
        'plan_code': (sub.plan.code if sub and sub.plan_id else ''),
    }
