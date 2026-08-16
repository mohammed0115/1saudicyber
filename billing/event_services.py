"""Idempotent inbox for provider payment events."""
from __future__ import annotations

import hashlib
import json

from django.db import IntegrityError, transaction
from django.utils import timezone

from billing.models import PaymentEvent, PaymentEventProcessing


def provider_event_key(provider, payload, payment_id='', provider_payment_id=''):
    """Return a stable event key that preserves distinct payment state changes.

    Providers do not always expose a separate webhook-event identifier. The
    canonical payload fingerprint remains safe for retries while including the
    provider payment, status and updated timestamp when present.
    """
    obj = payload.get('data') if isinstance(payload, dict) and isinstance(payload.get('data'), dict) else payload
    obj = obj if isinstance(obj, dict) else {}
    event_id = str(payload.get('event_id') or payload.get('id') or '') if isinstance(payload, dict) else ''
    provider_id = str(obj.get('id') or provider_payment_id or payment_id)
    status = str(obj.get('status') or '')
    updated = str(obj.get('updated_at') or obj.get('date') or '')
    canonical = json.dumps(payload if isinstance(payload, dict) else {}, sort_keys=True,
                           separators=(',', ':'), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]
    # Prefix makes operator tracing practical; digest makes same payment/status
    # events distinguishable when the provider omits a webhook id.
    return (event_id or f'{provider_id}:{status}:{updated}:{digest}')[:160]


def _safe_payload(payload):
    """Remove shared secrets and credential-shaped fields before persistence."""
    if not isinstance(payload, dict):
        return {}
    clean = json.loads(json.dumps(payload))
    for key in ('secret_token', 'token', 'authorization', 'signature'):
        clean.pop(key, None)
    return clean


def record_event(provider, payload, *, payment=None, company=None, signature_verified=False):
    """Append an inbound event once. Return ``(event, claimed)``.

    ``claimed=False`` means an identical event has already been accepted and
    must not trigger another state transition.
    """
    provider_id = getattr(payment, 'provider_payment_id', '') or ''
    key = provider_event_key(provider, payload, str(getattr(payment, 'id', '')), provider_id)
    obj = payload.get('data') if isinstance(payload, dict) and isinstance(payload.get('data'), dict) else payload
    event_type = str((obj or {}).get('status') or '')[:80] if isinstance(obj, dict) else ''
    try:
        with transaction.atomic():
            event = PaymentEvent.objects.create(
                company=company or getattr(payment, 'company', None),
                payment=payment,
                provider=provider,
                provider_event_id=key,
                event_type=event_type,
                payload=_safe_payload(payload),
                signature_verified=signature_verified,
            )
            PaymentEventProcessing.objects.create(event=event, status='processing', attempt_count=1)
            return event, True
    except IntegrityError:
        with transaction.atomic():
            event = PaymentEvent.objects.select_for_update().get(
                provider=provider, provider_event_id=key,
            )
            processing = PaymentEventProcessing.objects.select_for_update().get(event=event)
            if processing.status in ('deferred', 'failed'):
                processing.status = 'processing'
                processing.last_error = ''
                processing.attempt_count += 1
                processing.save(update_fields=['status', 'last_error', 'attempt_count', 'updated_at'])
                return event, True
            return event, False


def mark_event_outcome(event, *, status, error=''):
    """Record a mutable processing result without modifying the immutable event."""
    processing = PaymentEventProcessing.objects.select_for_update().get(event=event)
    processing.status = status
    processing.last_error = (error or '')[:500]
    processing.attempt_count += 1 if status == 'deferred' else 0
    if status == 'completed':
        processing.processed_at = timezone.now()
    processing.save(update_fields=['status', 'last_error', 'attempt_count', 'processed_at', 'updated_at'])
    return processing
