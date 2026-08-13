"""Connector lifecycle and deterministic automated-control-testing services.

Production provider drivers are intentionally not included. This module exposes a
safe mock driver and a stable interface that provider-specific packages can implement.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from django.db import transaction
from django.utils import timezone

from integrations.models import (
    ConnectorEvent,
    ControlTestDefinition,
    ControlTestResult,
    ControlTestRun,
    IntegrationConnection,
)


class ConnectorUnavailable(Exception):
    """Raised when a provider has no installed production driver."""


class BaseConnector:
    """Contract for a provider-specific connector implementation."""

    def __init__(self, connection: IntegrationConnection):
        self.connection = connection

    def test_connection(self) -> dict:
        raise NotImplementedError

    def run_control_test(self, definition: ControlTestDefinition) -> dict:
        raise NotImplementedError


class MockConnector(BaseConnector):
    """Deterministic development connector; it never contacts an external system."""

    def test_connection(self):
        healthy = self.connection.configuration.get('simulate_healthy', True)
        if healthy:
            return {'ok': True, 'message': 'Mock connection healthy.'}
        return {'ok': False, 'message': 'Mock connection intentionally unhealthy.'}

    def run_control_test(self, definition):
        outcome = definition.parameters.get('simulate_outcome', 'pass')
        if outcome not in {'pass', 'fail', 'warning', 'error'}:
            raise ValueError('simulate_outcome must be pass, fail, warning, or error.')
        return {
            'outcome': outcome,
            'summary': definition.parameters.get('summary', f'Mock test completed with {outcome}.'),
            'raw_result': {'provider': 'mock', 'outcome': outcome, 'parameters': definition.parameters},
        }


def get_connector(connection: IntegrationConnection) -> BaseConnector:
    if connection.provider.key == 'mock':
        return MockConnector(connection)
    raise ConnectorUnavailable(
        f"No production driver is installed for provider '{connection.provider.key}'. "
        'Use a reviewed provider package and an external credential vault before activation.'
    )


def test_connection(connection: IntegrationConnection) -> dict:
    """Validate a connection without ever reading a credential value from the database."""
    if connection.status in {'disabled', 'revoked'}:
        return {'ok': False, 'message': f'Connection is {connection.status}.'}
    try:
        result = get_connector(connection).test_connection()
    except (ConnectorUnavailable, Exception) as exc:
        connection.status = 'error'
        connection.last_error = str(exc)
        connection.last_checked_at = timezone.now()
        connection.save(update_fields=['status', 'last_error', 'last_checked_at', 'updated_at'])
        return {'ok': False, 'message': str(exc)}

    connection.last_checked_at = timezone.now()
    if result['ok']:
        connection.status = 'active'
        connection.last_error = ''
    else:
        connection.status = 'error'
        connection.last_error = result['message']
    connection.save(update_fields=['status', 'last_error', 'last_checked_at', 'updated_at'])
    return result


def _result_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _run_status(outcomes):
    if 'error' in outcomes:
        return 'error'
    if 'fail' in outcomes:
        return 'failed'
    if 'warning' in outcomes:
        return 'warning'
    return 'passed'


def execute_control_test(definition: ControlTestDefinition, *, trigger='manual', idempotency_key=None):
    """Execute an approved connector test and store one immutable result per mapped control."""
    if not definition.enabled:
        raise ValueError('Control test definition is disabled.')
    if definition.connection.status not in {'active', 'draft'}:
        raise ValueError(f'Connection is {definition.connection.status}.')

    idempotency_key = idempotency_key or f'{definition.id}:{trigger}:{uuid.uuid4()}'
    existing = ControlTestRun.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    with transaction.atomic():
        run = ControlTestRun.objects.create(
            definition=definition,
            company=definition.company,
            trigger=trigger,
            status='running',
            idempotency_key=idempotency_key,
            started_at=timezone.now(),
        )
        health = test_connection(definition.connection)
        if not health['ok']:
            run.status = 'error'
            run.error_message = health['message']
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'error_message', 'completed_at'])
            return run

        try:
            response = get_connector(definition.connection).run_control_test(definition)
            outcomes = []
            for control in definition.controls.select_related('framework'):
                payload = {
                    **response['raw_result'],
                    'control_id': control.control_id,
                    'framework': control.framework.code,
                    'run_id': run.id,
                }
                ControlTestResult.objects.create(
                    run=run,
                    control=control,
                    outcome=response['outcome'],
                    summary=response['summary'],
                    raw_result=payload,
                    evidence_uri=f'connector://{definition.connection.provider.key}/{definition.connection.id}/runs/{run.id}/{control.id}',
                    evidence_hash=_result_hash(payload),
                )
                outcomes.append(response['outcome'])
            run.status = _run_status(outcomes) if outcomes else 'warning'
        except Exception as exc:
            run.status = 'error'
            run.error_message = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'completed_at'])

    # Emit durable platform events only after the transaction committed the run and artifacts.
    if run.status in {'passed', 'failed', 'warning', 'error'}:
        from platform_events.services import process_test_run
        process_test_run(run)
    return run


def record_connector_event(connection: IntegrationConnection, event_type: str, payload: dict, *, idempotency_key: str):
    """Persist a schema-versioned connector event for subsequent orchestration."""
    event, _ = ConnectorEvent.objects.get_or_create(
        company=connection.company,
        idempotency_key=idempotency_key,
        defaults={
            'connection': connection,
            'event_type': event_type,
            'payload': payload,
        },
    )
    return event
