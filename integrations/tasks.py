"""Celery tasks for scheduled control testing and opt-in webhook delivery."""
from datetime import timedelta

import httpx
from celery import shared_task
from django.utils import timezone

from integrations.models import ControlTestDefinition
from integrations.services import execute_control_test
from platform_events.services import deliver_webhook, retryable_deliveries


@shared_task
def run_due_control_tests():
    """Run enabled definitions whose last run is older than their configured cadence."""
    now = timezone.now()
    summary = {'considered': 0, 'started': 0, 'skipped': 0, 'errors': 0}
    for definition in ControlTestDefinition.objects.filter(enabled=True).select_related('connection__provider'):
        summary['considered'] += 1
        latest = definition.runs.order_by('-created_at').first()
        reference_time = latest.created_at if latest else None
        if reference_time and reference_time > now - timedelta(minutes=definition.schedule_minutes):
            summary['skipped'] += 1
            continue
        try:
            execute_control_test(
                definition,
                trigger='scheduled',
                idempotency_key=f'scheduled:{definition.id}:{now:%Y%m%d%H%M}',
            )
            summary['started'] += 1
        except Exception:
            summary['errors'] += 1
    return summary


@shared_task
def deliver_due_webhooks():
    """Deliver configured events through HTTPS with HMAC signatures and bounded attempts."""
    summary = {'considered': 0, 'delivered': 0, 'failed': 0}
    for delivery in retryable_deliveries():
        summary['considered'] += 1
        result = deliver_webhook(delivery, http_post=httpx.post)
        if result.status == 'delivered':
            summary['delivered'] += 1
        else:
            summary['failed'] += 1
    return summary
