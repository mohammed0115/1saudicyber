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
