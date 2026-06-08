"""
Auditor Portal Models - Audit sessions, notes, findings
"""
from django.db import models
from core.models import Company, User
from compliance.models import Assessment, CompanyControl


class AuditorNote(models.Model):
    """Notes added by auditor during review."""
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='auditor_notes')
    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='auditor_portal_notes')
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_notes')
    note = models.TextField()
    is_finding = models.BooleanField(default=False)
    requires_action = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auditor_notes'
        ordering = ['-created_at']


class DocumentRequest(models.Model):
    """Auditor request for additional documents."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='document_requests')
    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='document_requests')
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_requests')
    description = models.TextField()
    description_ar = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'document_requests'


class AuditReport(models.Model):
    """Final audit report submitted by auditor."""
    assessment = models.OneToOneField(Assessment, on_delete=models.CASCADE, related_name='final_report')
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_reports')
    verdict = models.CharField(max_length=25, choices=[
        ('pass', 'Pass'), ('conditional_pass', 'Conditional Pass'), ('fail', 'Fail'),
    ])
    executive_summary = models.TextField()
    executive_summary_ar = models.TextField(blank=True)
    findings = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_reports'
