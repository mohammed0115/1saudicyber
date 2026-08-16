"""Phase 8I-C — Moyasar payment verification + webhook processing.

SECURITY / CORE RULE:
* A subscription is activated ONLY after a server-side Fetch-Payment verification
  confirms the payment is paid AND the amount, currency and internal metadata match
  our own Payment row. The browser callback never activates anything.
* The SECRET key is used only via billing.moyasar.fetch_moyasar_payment (server-side).
  It is never logged, returned to templates, or placed in audit metadata.
* No card data is stored. Only safe, non-sensitive provider fields are persisted.
* Every state change is idempotent and wrapped in transaction.atomic + row locking,
  so a duplicate webhook can never double-activate or duplicate state.
* Nothing here ever raises to the caller for a malformed payload — callers get a
  structured dict result and always return a safe HTTP response.
"""
import hmac

from django.db import transaction
from django.utils import timezone

from . import moyasar
from . import subscription_services as svc

# Moyasar status -> local Payment.status
_PAID = {'paid', 'captured', 'verified'}
_FAILED = {'failed'}
_REFUNDED = {'refunded'}
_CANCELLED = {'voided', 'cancelled'}
_PENDING = {'initiated', 'authorized'}


def map_moyasar_status(status):
    """Map a Moyasar payment status to a local status (or None if unknown)."""
    s = (status or '').strip().lower()
    if s in _PAID:
        return 'paid'
    if s in _FAILED:
        return 'failed'
    if s in _REFUNDED:
        return 'refunded'
    if s in _CANCELLED:
        return 'cancelled'
    if s in _PENDING:
        return 'pending'
    return None


def _payment_object(payload):
    """Return the Moyasar payment object from a webhook/API payload.

    Webhooks wrap the payment under ``data``; the Fetch API returns it flat.
    """
    if isinstance(payload, dict):
        data = payload.get('data')
        if isinstance(data, dict) and (data.get('id') or data.get('status') is not None):
            return data
        return payload
    return {}


def _expected_halalas(payment):
    try:
        return int((payment.amount or 0) * 100)
    except (TypeError, ValueError):
        return None


def verify_payload_matches(payment, payload):
    """True only if amount + currency + internal metadata all match our Payment.

    Fail-closed: any missing/unreadable field is a mismatch, so a forged or foreign
    payload can never satisfy verification.
    """
    obj = _payment_object(payload)
    expected = _expected_halalas(payment)
    if expected is None:
        return False, 'amount_unreadable'
    try:
        payload_amount = int(obj.get('amount'))
    except (TypeError, ValueError):
        return False, 'amount_unreadable'
    if payload_amount != expected:
        return False, 'amount_mismatch'
    if (obj.get('currency') or '').upper() != (payment.currency or '').upper():
        return False, 'currency_mismatch'
    meta = obj.get('metadata') or {}
    if not isinstance(meta, dict):
        return False, 'metadata_missing'
    if str(meta.get('internal_payment_id') or '') != str(payment.id):
        return False, 'payment_metadata_mismatch'
    if str(meta.get('company_id') or '') != str(payment.company_id):
        return False, 'company_mismatch'
    if payment.subscription_id and str(meta.get('subscription_id') or '') != str(payment.subscription_id):
        return False, 'subscription_mismatch'
    return True, 'ok'


def _merge_safe_metadata(payment, obj, source):
    """Persist ONLY safe, non-sensitive provider info. No card data, no secrets."""
    meta = dict(payment.provider_metadata or {})
    meta['last_provider_status'] = (obj.get('status') or '')[:40]
    meta['last_source'] = (source or '')[:20]
    payment.provider_metadata = meta


@transaction.atomic
def process_moyasar_payment_result(payment, provider_payload, actor=None, source='webhook',
                                   allow_activation=True):
    """Apply a verified Moyasar result to a Payment idempotently.

    ``provider_payload`` MUST be an authoritative payload (the caller fetched it from
    Moyasar) when ``allow_activation`` is True — activation trusts it as source of
    truth. With ``allow_activation`` False (e.g. Fetch failed) no paid activation can
    happen; only safe non-activating downgrades are recorded.
    """
    from .models import Payment
    locked = Payment.objects.select_for_update().get(pk=payment.pk)
    obj = _payment_object(provider_payload)
    ppid = str(obj.get('id') or '')[:128]
    provider_status = (obj.get('status') or '')
    target = map_moyasar_status(provider_status)
    result = {'ok': True, 'action': 'none', 'activated': False,
              'local_status': locked.status, 'provider_status': provider_status, 'reason': ''}

    if ppid and not locked.provider_payment_id:
        locked.provider_payment_id = ppid
    _merge_safe_metadata(locked, obj, source)
    fields = ['provider_payment_id', 'provider_metadata', 'status', 'paid_at', 'updated_at']

    # --- Idempotency: an already-paid payment is terminal for activation. ---
    if locked.status == 'paid':
        if target == 'refunded':
            locked.status = 'refunded'
            locked.save(update_fields=fields)
            _audit(actor, locked.company, 'moyasar_payment_refunded', locked, source, provider_status)
            result.update(action='refunded', local_status='refunded')
            return result
        locked.save(update_fields=fields)
        _audit(actor, locked.company, 'moyasar_webhook_received', locked, source, provider_status,
               extra={'note': 'duplicate_paid'})
        result.update(action='already_paid', local_status='paid')
        return result

    # --- Paid path: requires server-verified payload + full field match. ---
    if target == 'paid':
        ok, reason = verify_payload_matches(locked, provider_payload)
        if not ok:
            locked.save(update_fields=fields)
            _audit(actor, locked.company, 'moyasar_webhook_invalid', locked, source,
                   provider_status, extra={'reason': reason})
            result.update(action='rejected', reason=reason)
            return result
        _audit(actor, locked.company, 'moyasar_payment_verified', locked, source, provider_status)
        if not allow_activation:
            locked.save(update_fields=fields)
            _audit(actor, locked.company, 'moyasar_webhook_invalid', locked, source,
                   provider_status, extra={'reason': 'not_server_verified'})
            result.update(action='verified_not_activated', reason='not_server_verified')
            return result
        sub = locked.subscription
        if locked.status != 'pending' or sub is None or sub.status != 'pending_payment':
            locked.save(update_fields=fields)
            _audit(actor, locked.company, 'moyasar_webhook_received', locked, source,
                   provider_status, extra={'note': 'not_activatable'})
            result.update(action='not_activatable',
                          reason='payment_or_subscription_not_pending')
            return result
        # Verified + valid + activatable -> mark paid and activate.
        locked.status = 'paid'
        locked.paid_at = timezone.now()
        locked.save(update_fields=fields)
        svc.activate_subscription(sub, actor=actor, reason='moyasar payment verified')
        _audit(actor, locked.company, 'moyasar_payment_paid', locked, source, provider_status)
        _audit(actor, locked.company, 'subscription_activated_from_moyasar', locked, source,
               provider_status, extra={'subscription_id': sub.id})
        result.update(action='activated', activated=True, local_status='paid')
        return result

    # --- Non-activating outcomes (safe even without server verification). ---
    if target in ('failed', 'cancelled'):
        if locked.status == 'pending':
            locked.status = target
        locked.save(update_fields=fields)
        _audit(actor, locked.company, 'moyasar_payment_failed', locked, source, provider_status)
        result.update(action=target, local_status=locked.status)
        return result

    if target == 'refunded':
        locked.status = 'refunded'
        locked.save(update_fields=fields)
        _audit(actor, locked.company, 'moyasar_payment_refunded', locked, source, provider_status)
        result.update(action='refunded', local_status='refunded')
        return result

    # initiated / authorized / unknown -> keep pending.
    locked.save(update_fields=fields)
    _audit(actor, locked.company, 'moyasar_webhook_received', locked, source, provider_status,
           extra={'note': 'kept_pending'})
    result.update(action='pending', local_status=locked.status)
    return result


def verify_moyasar_payment(payment, actor=None, source='verification'):
    """Fetch the payment from Moyasar (server-side) and apply the result. Never raises."""
    if payment is None:
        return {'ok': False, 'action': 'none', 'reason': 'no_payment'}
    if not payment.provider_payment_id:
        return {'ok': False, 'action': 'none', 'reason': 'no_provider_id'}
    fetched = moyasar.fetch_moyasar_payment(payment.provider_payment_id)
    if not fetched.get('ok'):
        _audit(actor, payment.company, 'moyasar_webhook_invalid', payment, source, '',
               extra={'reason': 'fetch_failed:%s' % fetched.get('error', '')})
        return {'ok': False, 'action': 'none', 'reason': 'fetch_failed'}
    return process_moyasar_payment_result(payment, fetched['payload'], actor=actor,
                                          source=source, allow_activation=True)


def process_moyasar_webhook(payload, headers=None):
    """Process an incoming Moyasar webhook payload. Returns a dict with http_status.

    Flow: optional shared-secret check -> extract provider id / internal id -> find our
    Payment -> server-side Fetch to get the authoritative payload -> apply the result.
    A forged webhook cannot activate because activation depends on the Fetch result and
    the metadata/amount/currency match, not on the incoming body.
    """
    from .models import Payment
    obj = _payment_object(payload)
    provider_status = (obj.get('status') or '') if isinstance(obj, dict) else ''
    _audit(None, None, 'moyasar_webhook_received', None, 'webhook', provider_status)

    # Live payments require an authenticated webhook before any identifier is trusted.
    expected = moyasar.webhook_secret()
    if moyasar.is_live() and not expected:
        _audit(None, None, 'moyasar_webhook_invalid', None, 'webhook', provider_status,
               extra={'reason': 'webhook_secret_not_configured'})
        return {'ok': False, 'action': 'rejected', 'http_status': 503,
                'reason': 'webhook_secret_not_configured'}
    if expected:
        provided = str(payload.get('secret_token') or '') if isinstance(payload, dict) else ''
        if not provided and headers is not None:
            try:
                provided = headers.get('X-Moyasar-Token') or headers.get('X-Event-Secret') or ''
            except Exception:
                provided = ''
        if not hmac.compare_digest(str(provided), str(expected)):
            _audit(None, None, 'moyasar_webhook_invalid', None, 'webhook', provider_status,
                   extra={'reason': 'secret_mismatch'})
            return {'ok': False, 'action': 'rejected', 'http_status': 403, 'reason': 'secret_mismatch'}

    ppid = str(obj.get('id') or '')[:128] if isinstance(obj, dict) else ''
    meta = obj.get('metadata') or {} if isinstance(obj, dict) else {}
    ipid = str(meta.get('internal_payment_id') or '') if isinstance(meta, dict) else ''
    if not ppid and not ipid:
        _audit(None, None, 'moyasar_webhook_invalid', None, 'webhook', provider_status,
               extra={'reason': 'no_identifiers'})
        return {'ok': False, 'action': 'invalid', 'http_status': 400, 'reason': 'no_identifiers'}

    payment = None
    if ppid:
        payment = Payment.objects.filter(provider='moyasar', provider_payment_id=ppid).first()
    if payment is None and ipid.isdigit():
        payment = Payment.objects.filter(provider='moyasar', id=int(ipid)).first()
    if payment is None:
        _audit(None, None, 'moyasar_webhook_invalid', None, 'webhook', provider_status,
               extra={'reason': 'unknown_payment'})
        return {'ok': True, 'action': 'ignored', 'http_status': 200, 'reason': 'unknown_payment'}

    # Server-side Fetch is the source of truth for activation.
    fetch_id = ppid or payment.provider_payment_id
    fetched = moyasar.fetch_moyasar_payment(fetch_id) if fetch_id else {'ok': False, 'error': 'no_id'}
    if not fetched.get('ok'):
        # Do not trust the inbound body for *any* state transition when the provider is unavailable.
        _audit(None, payment.company, 'moyasar_webhook_invalid', payment, 'webhook',
               provider_status, extra={'reason': 'fetch_failed:%s' % fetched.get('error', '')})
        return {'ok': False, 'action': 'deferred', 'http_status': 503, 'reason': 'fetch_failed'}

    result = process_moyasar_payment_result(payment, fetched['payload'], source='webhook',
                                            allow_activation=True)
    result['http_status'] = 200
    return result


# ---------------------------------------------------------------------------
# Audit (safe metadata only; never blocks processing)
# ---------------------------------------------------------------------------
def _audit(actor, company, action, payment, source, provider_status, extra=None):
    try:
        from core.models import AuditLog
        meta = {
            'company_id': getattr(company, 'id', None),
            'payment_id': getattr(payment, 'id', None),
            'subscription_id': getattr(payment, 'subscription_id', None) if payment else None,
            'provider_payment_id': getattr(payment, 'provider_payment_id', '') if payment else '',
            'provider_status': (provider_status or '')[:40],
            'amount': str(getattr(payment, 'amount', '')) if payment else '',
            'currency': getattr(payment, 'currency', '') if payment else '',
            'source': (source or '')[:20],
            'performed_by': getattr(actor, 'email', ''),
        }
        if extra:
            meta.update(extra)
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=action[:100], path='/billing/moyasar/webhook/', metadata=meta)
    except Exception:
        pass
