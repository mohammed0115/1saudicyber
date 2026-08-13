"""Versioned policy, common-control mapping, and reproducible decision models."""
from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PolicyPack(models.Model):
    """A reusable regulatory or domain policy package."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('retired', 'Retired'),
    ]

    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'policy_packs'
        ordering = ['key']

    def __str__(self):
        return self.key


class PolicyVersion(models.Model):
    """An immutable-by-convention, source-traceable set of applicability rules."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('retired', 'Retired'),
    ]

    policy_pack = models.ForeignKey(PolicyPack, on_delete=models.CASCADE, related_name='versions')
    version = models.CharField(max_length=40)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    source_reference = models.URLField(blank=True)
    rules = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, editable=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_policy_versions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'policy_versions'
        ordering = ['policy_pack__key', '-effective_from', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['policy_pack', 'version'], name='unique_policy_pack_version'),
        ]

    def __str__(self):
        return f'{self.policy_pack.key}@{self.version}'

    @staticmethod
    def hash_rules(rules):
        canonical = json.dumps(rules or [], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def clean(self):
        if not isinstance(self.rules, list):
            raise ValidationError({'rules': 'Rules must be a JSON array.'})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({'effective_to': 'Effective end date cannot precede effective start date.'})
        for index, rule in enumerate(self.rules):
            if not isinstance(rule, dict) or not rule.get('id'):
                raise ValidationError({'rules': f'Rule {index} must be an object with an id.'})
            if not isinstance(rule.get('include_control_ids', []), list):
                raise ValidationError({'rules': f'Rule {rule.get("id", index)} must include a control-id list.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        self.content_hash = self.hash_rules(self.rules)
        if self.status == 'approved' and not self.approved_at:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)

    def is_effective_on(self, on_date=None):
        on_date = on_date or timezone.localdate()
        return (
            self.status == 'approved'
            and self.effective_from <= on_date
            and (self.effective_to is None or self.effective_to >= on_date)
        )


class CanonicalControl(models.Model):
    """A framework-neutral objective used by the common-controls optimizer."""

    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'canonical_controls'
        ordering = ['key']

    def __str__(self):
        return self.key


class ControlCoverageMapping(models.Model):
    """A versioned, reviewable mapping from a framework control to a canonical objective."""

    RELATIONSHIP_CHOICES = [
        ('equivalent', 'Equivalent'),
        ('partial', 'Partial'),
        ('supports', 'Supports'),
    ]

    canonical_control = models.ForeignKey(CanonicalControl, on_delete=models.CASCADE, related_name='mappings')
    control = models.ForeignKey('compliance.Control', on_delete=models.CASCADE, related_name='canonical_mappings')
    policy_version = models.ForeignKey(PolicyVersion, on_delete=models.PROTECT, related_name='coverage_mappings')
    relationship = models.CharField(max_length=16, choices=RELATIONSHIP_CHOICES)
    coverage_score = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    rationale = models.TextField()
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_control_mappings',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_coverage_mappings'
        constraints = [
            models.UniqueConstraint(
                fields=['canonical_control', 'control', 'policy_version'],
                name='unique_canonical_control_mapping_version',
            ),
        ]

    def clean(self):
        if not 0 <= self.coverage_score <= 100:
            raise ValidationError({'coverage_score': 'Coverage score must be between 0 and 100.'})


class PolicyEvaluation(models.Model):
    """A replayable policy-evaluation record with input and decision hashes."""

    company = models.ForeignKey(
        'core.Company', null=True, blank=True, on_delete=models.SET_NULL, related_name='policy_evaluations',
    )
    policy_version = models.ForeignKey(PolicyVersion, on_delete=models.PROTECT, related_name='evaluations')
    input_data = models.JSONField(default=dict)
    result_data = models.JSONField(default=dict)
    input_hash = models.CharField(max_length=64, db_index=True)
    decision_hash = models.CharField(max_length=64, db_index=True)
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='policy_evaluations',
    )
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'policy_evaluations'
        ordering = ['-evaluated_at']

    @staticmethod
    def hash_payload(payload):
        canonical = json.dumps(payload or {}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        self.input_hash = self.hash_payload(self.input_data)
        self.decision_hash = self.hash_payload(self.result_data)
        super().save(*args, **kwargs)
