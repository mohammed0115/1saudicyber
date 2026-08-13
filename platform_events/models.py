"""Durable domain events, webhook subscriptions, and reviewable remediation recommendations."""
from __future__ import annotations

import uuid
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import models


class DomainEvent(models.Model):
    """An outbox record that is the reliable source of integration events."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('published', 'Published'),
        ('failed', 'Failed'),
        ('dead_letter', 'Dead Letter'),
    ]

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='domain_events')
    event_type = models.CharField(max_length=120)
    schema_version = models.CharField(max_length=32, default='1.0')
    payload = models.JSONField(default=dict)
    trace_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    available_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'domain_events'
        constraints = [
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_domain_event_idempotency'),
        ]
        ordering = ['created_at']


class WebhookSubscription(models.Model):
    """A tenant-owned outbound webhook configuration, without storing the signing secret."""

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='webhook_subscriptions')
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    event_types = models.JSONField(default=list)
    signing_secret_reference = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhook_subscriptions'
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='unique_company_webhook_name'),
        ]

    def clean(self):
        parsed = urlparse(self.url)
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValidationError({'url': 'Webhook URLs must use HTTPS and include a hostname.'})
        blocked = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
        if parsed.hostname.lower() in blocked:
            raise ValidationError({'url': 'Webhook URL cannot point to a local host.'})
        if not isinstance(self.event_types, list) or not all(isinstance(item, str) for item in self.event_types):
            raise ValidationError({'event_types': 'Event types must be a JSON array of strings.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class WebhookDelivery(models.Model):
    """Delivery attempt record; payload is read from the immutable DomainEvent."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('dead_letter', 'Dead Letter'),
    ]

    event = models.ForeignKey(DomainEvent, on_delete=models.CASCADE, related_name='deliveries')
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name='deliveries')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    attempt_count = models.PositiveIntegerField(default=0)
    response_status = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook_deliveries'
        constraints = [
            models.UniqueConstraint(fields=['event', 'subscription'], name='unique_event_webhook_delivery'),
        ]


class ControlStatusRecommendation(models.Model):
    """A test-generated proposed control status that needs accountable human acceptance."""

    STATUS_CHOICES = [
        ('pending', 'Pending review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    test_result = models.OneToOneField(
        'integrations.ControlTestResult', on_delete=models.CASCADE, related_name='status_recommendation',
    )
    company_control = models.ForeignKey(
        'compliance.CompanyControl', on_delete=models.CASCADE, related_name='status_recommendations',
    )
    proposed_status = models.CharField(max_length=25)
    rule_reference = models.CharField(max_length=255)
    rationale = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        'core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_status_recommendations',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_status_recommendations'
