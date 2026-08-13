"""Outbox, remediation, and webhook-planning services.

Outbound delivery is opt-in: an active HTTPS subscription and an externally
resolved signing secret are both required before network delivery is attempted.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from monitoring.models import Alert
from platform_events.models import (
    ControlStatusRecommendation,
    DomainEvent,
    WebhookDelivery,
    WebhookSubscription,
)


def emit_event(company, event_type: str, payload: dict, *, idempotency_key: str, trace_id=None):
    """Create one durable, schema-versioned event and plan matching deliveries."""
    defaults = {'event_type': event_type, 'payload': payload}
    if trace_id:
        defaults['trace_id'] = trace_id
    with transaction.atomic():
        event, created = DomainEvent.objects.get_or_create(
            company=company,
            idempotency_key=idempotency_key,
            defaults=defaults,
        )
        if created:
            subscriptions = WebhookSubscription.objects.filter(company=company, is_active=True)
            for subscription in subscriptions:
                if '*' in subscription.event_types or event_type in subscription.event_types:
                    WebhookDelivery.objects.get_or_create(event=event, subscription=subscription)
    return event


def recommend_from_test_result(test_result):
    """Generate reviewable status recommendations; never auto-accept an AI/connector decision."""
    outcome_to_status = {
        'pass': 'compliant',
        'fail': 'non_compliant',
        'warning': 'partially_compliant',
    }
    proposed = outcome_to_status.get(test_result.outcome)
    if not proposed:
        return None
    from compliance.models import CompanyControl

    company_control = CompanyControl.objects.get(
        company=test_result.run.company,
        control=test_result.control,
    )
    recommendation, created = ControlStatusRecommendation.objects.get_or_create(
        test_result=test_result,
        defaults={
            'company_control': company_control,
            'proposed_status': proposed,
            'rule_reference': 'automated-control-testing/v1',
            'rationale': test_result.summary,
        },
    )
    if created and test_result.outcome == 'fail':
        Alert.objects.create(
            company=test_result.run.company,
            alert_type='system',
            severity='high',
            title=f'Automated control test failed: {test_result.control.control_id}',
            title_ar=f'فشل اختبار الضابط المؤتمت: {test_result.control.control_id}',
            description=test_result.summary,
            description_ar=test_result.summary,
            affected_control=test_result.control.control_id,
        )
    return recommendation


def process_test_run(run):
    """Translate a completed test run into events, alerts, and pending recommendations."""
    if run.status not in {'passed', 'failed', 'warning', 'error'}:
        return []
    emitted = []
    for result in run.results.select_related('control'):
        recommendation = recommend_from_test_result(result)
        event = emit_event(
            run.company,
            'control.test.completed',
            {
                'run_id': run.id,
                'definition_key': run.definition.key,
                'control_id': result.control.control_id,
                'outcome': result.outcome,
                'evidence_uri': result.evidence_uri,
                'evidence_hash': result.evidence_hash,
                'recommendation_id': recommendation.id if recommendation else None,
            },
            idempotency_key=f'control-test-result:{result.id}',
            trace_id=run.trace_id,
        )
        emitted.append(event)
    return emitted


def review_status_recommendation(recommendation, *, reviewer, accept: bool):
    """Apply a proposed state only after an authorised human review."""
    if recommendation.status != 'pending':
        raise ValueError('Recommendation has already been reviewed.')
    recommendation.status = 'accepted' if accept else 'rejected'
    recommendation.reviewed_by = reviewer
    recommendation.reviewed_at = timezone.now()
    recommendation.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    if accept:
        company_control = recommendation.company_control
        company_control.status = recommendation.proposed_status
        company_control.last_assessed = timezone.now()
        company_control.save(update_fields=['status', 'last_assessed', 'updated_at'])
    return recommendation


def _resolve_webhook_secret(reference):
    """Development resolver. Production must replace this with a KMS/vault adapter."""
    if not reference:
        return None
    env_key = 'WEBHOOK_SECRET_' + ''.join(ch if ch.isalnum() else '_' for ch in reference.upper())
    return os.getenv(env_key)


def deliver_webhook(delivery, *, http_post):
    """Deliver one event through a caller-provided HTTP function, enabling safe testing."""
    secret = _resolve_webhook_secret(delivery.subscription.signing_secret_reference)
    if not secret:
        delivery.status = 'failed'
        delivery.last_error = 'No signing secret resolved for webhook subscription.'
        delivery.attempt_count += 1
        delivery.save(update_fields=['status', 'last_error', 'attempt_count'])
        return delivery

    envelope = {
        'id': str(delivery.event.event_id),
        'type': delivery.event.event_type,
        'schema_version': delivery.event.schema_version,
        'trace_id': str(delivery.event.trace_id),
        'created_at': delivery.event.created_at.isoformat(),
        'data': delivery.event.payload,
    }
    body = json.dumps(envelope, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    try:
        response = http_post(
            delivery.subscription.url,
            data=body,
            headers={
                'Content-Type': 'application/json',
                'X-Platform-Event-ID': str(delivery.event.event_id),
                'X-Platform-Signature': f'sha256={signature}',
            },
            timeout=10,
        )
        delivery.attempt_count += 1
        delivery.response_status = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = 'delivered'
            delivery.delivered_at = timezone.now()
            delivery.last_error = ''
        else:
            delivery.status = 'failed'
            delivery.last_error = f'Webhook returned HTTP {response.status_code}.'
    except Exception as exc:
        delivery.attempt_count += 1
        delivery.status = 'failed'
        delivery.last_error = str(exc)
    delivery.save(update_fields=['status', 'attempt_count', 'response_status', 'last_error', 'delivered_at'])
    return delivery


def retryable_deliveries(max_attempts=5):
    """Return due deliveries; scheduler/worker wiring decides when to call them."""
    return WebhookDelivery.objects.filter(status__in=['pending', 'failed'], attempt_count__lt=max_attempts)
