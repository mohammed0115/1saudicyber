"""
Monitoring Models - Continuous compliance monitoring and alerts
"""
from django.db import models
from core.models import Company


class ComplianceScore(models.Model):
    """Daily compliance score snapshot."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='score_history')
    date = models.DateField()
    overall_score = models.FloatField(default=0.0)
    nca_score = models.FloatField(default=0.0)
    aramco_score = models.FloatField(default=0.0)
    sabic_score = models.FloatField(default=0.0)
    controls_compliant = models.IntegerField(default=0)
    controls_total = models.IntegerField(default=0)

    class Meta:
        db_table = 'compliance_scores'
        unique_together = ['company', 'date']
        ordering = ['-date']


class Alert(models.Model):
    """Real-time compliance alert."""
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('info', 'Informational'),
    ]

    TYPE_CHOICES = [
        ('drift', 'Configuration Drift'),
        ('access_change', 'Access Control Change'),
        ('score_drop', 'Score Drop'),
        ('certificate_expiry', 'Certificate Expiry'),
        ('new_vulnerability', 'New Vulnerability'),
        ('policy_change', 'Policy Change'),
        ('system', 'System Alert'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    title = models.CharField(max_length=300)
    title_ar = models.CharField(max_length=300, blank=True)
    description = models.TextField()
    description_ar = models.TextField(blank=True)
    affected_control = models.CharField(max_length=50, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'alerts'
        ordering = ['-created_at']
        # Hot tenant path: filter(company).order_by('-created_at')[:N] in dashboards/hub.
        # Unlike ComplianceScore/MonthlyReport (covered by their unique_together composite),
        # Alert had only the FK index -> a filesort on created_at at scale. Index it.
        indexes = [
            models.Index(fields=['company', '-created_at'], name='alert_company_created_idx'),
        ]


class MonthlyReport(models.Model):
    """Auto-generated monthly compliance report."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='monthly_reports')
    month = models.DateField()
    report_data = models.JSONField(default=dict)
    summary_en = models.TextField(blank=True)
    summary_ar = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'monthly_reports'
        unique_together = ['company', 'month']
        ordering = ['-month']


class CertificateTracker(models.Model):
    """Track certificate renewal dates."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='certificates')
    framework_code = models.CharField(max_length=50)
    certificate_number = models.CharField(max_length=100, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    days_remaining = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'certificate_trackers'


# ============================================================
# Phase 5B — Continuous Monitoring Foundation (additive).
# Deterministic, internal-only. NEVER changes ControlAssessment decisions,
# never calls AI/LLM or external networks, never imports OTCC/DCC.
# ============================================================
from core.models import User


class MonitoringCheck(models.Model):
    """A recurring monitoring check for a company (optionally tied to a control)."""
    CHECK_TYPES = [
        ('evidence_freshness', 'Evidence Freshness'),
        ('remediation_overdue', 'Remediation Overdue'),
        ('risk_review', 'Risk Review'),
        ('manual_review', 'Manual Review'),
        ('policy_review', 'Policy Review'),
        ('control_status_review', 'Control Status Review'),
    ]
    FREQUENCIES = [
        ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'), ('semi_annual', 'Semi-annual'), ('annual', 'Annual'),
    ]
    STATUS_CHOICES = [('active', 'Active'), ('paused', 'Paused'), ('archived', 'Archived')]
    RESULT_CHOICES = [
        ('pass', 'Pass'), ('fail', 'Fail'), ('needs_review', 'Needs Review'), ('not_run', 'Not Run')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='monitoring_checks')
    framework_version = models.ForeignKey(
        'compliance.FrameworkVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='monitoring_checks')
    control = models.ForeignKey(
        'compliance.Control', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='monitoring_checks')
    control_assessment = models.ForeignKey(
        'compliance.ControlAssessment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='monitoring_checks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    check_type = models.CharField(max_length=30, choices=CHECK_TYPES, default='manual_review')
    frequency = models.CharField(max_length=20, choices=FREQUENCIES, default='monthly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='not_run')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_monitoring_checks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'monitoring_checks'
        ordering = ['next_run_at', '-created_at']

    def __str__(self):
        return f"{self.company_id}:{self.title} ({self.check_type})"

    def is_due(self, now):
        return self.status == 'active' and (self.next_run_at is None or self.next_run_at <= now)


class MonitoringRun(models.Model):
    """One execution of a monitoring check."""
    STATUS_CHOICES = [
        ('pass', 'Pass'), ('fail', 'Fail'), ('needs_review', 'Needs Review'), ('error', 'Error')]

    monitoring_check = models.ForeignKey(MonitoringCheck, on_delete=models.CASCADE, related_name='runs')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='monitoring_runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='needs_review')
    summary = models.CharField(max_length=300, blank=True)
    details = models.TextField(blank=True)
    evidence_snapshot = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'monitoring_runs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Run[{self.monitoring_check_id}] = {self.status}"


class MonitoringFinding(models.Model):
    """An actionable issue found by a monitoring run."""
    SEVERITY_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    STATUS_CHOICES = [
        ('open', 'Open'), ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'), ('false_positive', 'False Positive')]
    OPEN_STATUSES = ('open', 'acknowledged')

    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE, related_name='findings')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='monitoring_findings')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    related_risk = models.ForeignKey(
        'risk.RiskItem', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='monitoring_findings')
    related_remediation_task = models.ForeignKey(
        'risk.RemediationTask', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='monitoring_findings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'monitoring_findings'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.severity}:{self.title}"
