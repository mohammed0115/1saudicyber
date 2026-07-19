"""
Phase 5A — Risk Register & Remediation Plan (additive).

Deterministic risk scoring (likelihood * impact). NEVER changes ControlAssessment,
never lets AI decide compliance, never creates CompanyControl. Tenant-scoped by
company. AI/assessment links are advisory provenance only.
"""
from django.db import models

from core.models import Company, User


def severity_for_score(score):
    """Deterministic severity mapping: 1-4 low, 5-9 medium, 10-16 high, 17-25 critical."""
    score = score or 0
    if score <= 4:
        return 'low'
    if score <= 9:
        return 'medium'
    if score <= 16:
        return 'high'
    return 'critical'


class RiskItem(models.Model):
    SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('control_assessment', 'Control Assessment'),
        ('evidence_analysis', 'Evidence Analysis'),
        ('gap_analysis', 'Gap Analysis'),
        ('auditor_finding', 'Auditor Finding'),
    ]
    CATEGORY_CHOICES = [
        ('governance', 'Governance'),
        ('access_control', 'Access Control'),
        ('incident_response', 'Incident Response'),
        ('cloud_security', 'Cloud Security'),
        ('third_party', 'Third Party'),
        ('data_protection', 'Data Protection'),
        ('business_continuity', 'Business Continuity'),
        ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    SEVERITY_LABELS_AR = {'low': 'منخفض', 'medium': 'متوسط', 'high': 'عالي', 'critical': 'حرج'}
    STATUS_CHOICES = [
        ('open', 'Open'), ('in_progress', 'In Progress'), ('mitigated', 'Mitigated'),
        ('accepted', 'Accepted'), ('closed', 'Closed')]
    OPEN_STATUSES = ('open', 'in_progress')
    LIKELIHOOD_CHOICES = [(i, str(i)) for i in range(1, 6)]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='risk_items')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='manual')

    framework_version = models.ForeignKey(
        'compliance.FrameworkVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='risk_items')
    control = models.ForeignKey(
        'compliance.Control', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='risk_items')
    control_assessment = models.ForeignKey(
        'compliance.ControlAssessment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='risk_items')
    evidence_submission = models.ForeignKey(
        'compliance.EvidenceSubmission', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='risk_items')
    evidence_analysis_result = models.ForeignKey(
        'compliance.EvidenceAnalysisResult', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='risk_items')

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    likelihood = models.PositiveSmallIntegerField(choices=LIKELIHOOD_CHOICES, default=1)
    impact = models.PositiveSmallIntegerField(choices=LIKELIHOOD_CHOICES, default=1)
    inherent_score = models.PositiveSmallIntegerField(default=1)
    residual_likelihood = models.PositiveSmallIntegerField(choices=LIKELIHOOD_CHOICES, null=True, blank=True)
    residual_impact = models.PositiveSmallIntegerField(choices=LIKELIHOOD_CHOICES, null=True, blank=True)
    residual_score = models.PositiveSmallIntegerField(null=True, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='low')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    owner_name = models.CharField(max_length=160, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_risks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'risk_items'
        ordering = ['-inherent_score', '-created_at']
        indexes = [models.Index(fields=['company', 'status'])]   # DD: tenant risk-register scans

    def __str__(self):
        return f"{self.company_id}:{self.title} ({self.severity})"

    def save(self, *args, **kwargs):
        # Deterministic scoring; severity derives from the inherent score.
        self.inherent_score = (self.likelihood or 0) * (self.impact or 0)
        if self.residual_likelihood and self.residual_impact:
            self.residual_score = self.residual_likelihood * self.residual_impact
        else:
            self.residual_score = None
        self.severity = severity_for_score(self.inherent_score)
        super().save(*args, **kwargs)

    @property
    def score(self):
        return (self.likelihood or 0) * (self.impact or 0)

    @property
    def severity_label_ar(self):
        return self.SEVERITY_LABELS_AR.get(self.severity, self.severity)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES


class RemediationTask(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')]
    STATUS_CHOICES = [
        ('todo', 'To Do'), ('in_progress', 'In Progress'), ('blocked', 'Blocked'),
        ('done', 'Done'), ('cancelled', 'Cancelled')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='remediation_tasks')
    risk = models.ForeignKey(RiskItem, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner_name = models.CharField(max_length=160, blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    verification_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_remediation_tasks')
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'remediation_tasks'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.status})"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.status == 'done' and self.completed_at is None:
            self.completed_at = timezone.now()
        if self.status != 'done':
            self.completed_at = None
        super().save(*args, **kwargs)
