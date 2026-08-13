"""Models for connector lifecycle and automated control-testing evidence."""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class IntegrationProvider(models.Model):
    """A provider catalogue entry; it never stores tenant credentials."""

    AUTH_CHOICES = [
        ('oauth2', 'OAuth 2.0'),
        ('api_key', 'API Key'),
        ('service_account', 'Service Account'),
        ('manual', 'Manual Upload'),
        ('mock', 'Mock/Test Connector'),
    ]

    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    auth_type = models.CharField(max_length=24, choices=AUTH_CHOICES)
    config_schema = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'integration_providers'
        ordering = ['name']

    def __str__(self):
        return self.key


class IntegrationConnection(models.Model):
    """A tenant-specific connection. Credential material stays in an external vault."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('disabled', 'Disabled'),
        ('revoked', 'Revoked'),
        ('error', 'Error'),
    ]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='integration_connections')
    provider = models.ForeignKey(IntegrationProvider, on_delete=models.PROTECT, related_name='connections')
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    credential_reference = models.CharField(max_length=255, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_connections',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'integration_connections'
        constraints = [
            models.UniqueConstraint(fields=['company', 'provider', 'name'], name='unique_company_provider_connection'),
        ]
        ordering = ['company_id', 'name']

    def clean(self):
        blocked = {'secret', 'token', 'password', 'api_key', 'private_key'}
        overlap = blocked.intersection({str(key).lower() for key in self.configuration.keys()})
        if overlap:
            raise ValidationError({
                'configuration': 'Secrets must be stored in an external vault and referenced by credential_reference.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.company_id}:{self.provider.key}:{self.name}'


class ConnectorEvent(models.Model):
    """An append-only event received from or emitted for a connector."""

    STATUS_CHOICES = [
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('dead_letter', 'Dead Letter'),
    ]

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='connector_events')
    connection = models.ForeignKey(
        IntegrationConnection, null=True, blank=True, on_delete=models.SET_NULL, related_name='events',
    )
    event_type = models.CharField(max_length=120)
    schema_version = models.CharField(max_length=32, default='1.0')
    payload = models.JSONField(default=dict)
    trace_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='received')
    processing_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'connector_events'
        constraints = [
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_connector_event_idempotency'),
        ]
        ordering = ['-created_at']


class ControlTestDefinition(models.Model):
    """A scheduled or on-demand test mapped to one or more compliance controls."""

    key = models.SlugField(max_length=100)
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='control_test_definitions')
    connection = models.ForeignKey(IntegrationConnection, on_delete=models.PROTECT, related_name='test_definitions')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    controls = models.ManyToManyField('compliance.Control', related_name='test_definitions')
    schedule_minutes = models.PositiveIntegerField(default=1440)
    parameters = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_control_tests',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'control_test_definitions'
        constraints = [
            models.UniqueConstraint(fields=['company', 'key'], name='unique_company_control_test_key'),
        ]
        ordering = ['company_id', 'key']

    def clean(self):
        if self.connection_id and self.company_id and self.connection.company_id != self.company_id:
            raise ValidationError({'connection': 'The connector must belong to the same company as the test.'})
        if not 15 <= self.schedule_minutes <= 1440:
            raise ValidationError({'schedule_minutes': 'The schedule must be between 15 minutes and 24 hours.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ControlTestRun(models.Model):
    """One isolated execution of a control-test definition."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('cancelled', 'Cancelled'),
    ]

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
        ('event', 'Event'),
    ]

    definition = models.ForeignKey(ControlTestDefinition, on_delete=models.CASCADE, related_name='runs')
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='control_test_runs')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    trigger = models.CharField(max_length=16, choices=TRIGGER_CHOICES, default='manual')
    trace_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_test_runs'
        ordering = ['-created_at']


class ControlTestResult(models.Model):
    """Per-control test outcome with immutable evidence metadata."""

    OUTCOME_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    run = models.ForeignKey(ControlTestRun, on_delete=models.CASCADE, related_name='results')
    control = models.ForeignKey('compliance.Control', on_delete=models.PROTECT, related_name='test_results')
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES)
    summary = models.TextField()
    raw_result = models.JSONField(default=dict, blank=True)
    evidence_uri = models.CharField(max_length=500, blank=True)
    evidence_hash = models.CharField(max_length=64, blank=True)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_test_results'
        constraints = [
            models.UniqueConstraint(fields=['run', 'control'], name='unique_test_result_per_control'),
        ]
