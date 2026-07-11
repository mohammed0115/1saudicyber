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
    """Auditor Request-for-Information (RFI) / request for additional evidence.

    UAT-...-RFI-LOOP-C: extended with an RFI lifecycle (open/responded/under_review/
    closed/cancelled), title, priority, and closing note. All additions are additive;
    no existing field was renamed or removed. This is an INTERNAL review artefact,
    never an official certification request.
    """
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('responded', 'Responded'),
        ('under_review', 'Under Review'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
        # legacy value kept for rows created before the RFI lifecycle existed.
        ('pending', 'Pending'),
    ]
    PRIORITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]
    OPEN_STATES = ('open', 'pending', 'responded', 'under_review')

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='document_requests')
    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='document_requests')
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_requests')
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    description_ar = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    closing_note = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'document_requests'

    def is_open(self):
        return self.status in self.OPEN_STATES


class CompanyRFIResponse(models.Model):
    """A company's response to an auditor RFI (text + optional link to existing evidence)."""
    request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='responses')
    responder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='rfi_responses')
    response_text = models.TextField()
    linked_evidence = models.ForeignKey('compliance.Evidence', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='rfi_responses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_rfi_responses'
        ordering = ['-created_at']


class AuditorControlVerdict(models.Model):
    """The auditor's INTERNAL verdict for one control within an assessment.

    Internal readiness review only — never an official NCA/Aramco/SABIC certification.
    One current verdict per (assessment, company_control); updates overwrite in place
    (history is a future enhancement).
    """
    STATUS_CHOICES = [
        ('not_reviewed', 'Not Reviewed'),
        ('compliant', 'Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('needs_more_evidence', 'Needs More Evidence'),
        ('not_applicable', 'Not Applicable'),
    ]
    IMPACT_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    # Statuses that count as a completed internal review of the control.
    REVIEWED_STATES = ('compliant', 'partially_compliant', 'non_compliant',
                       'needs_more_evidence', 'not_applicable')

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='control_verdicts')
    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='auditor_verdicts')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='control_verdicts')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='not_reviewed')
    rationale = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    impact = models.CharField(max_length=10, choices=IMPACT_CHOICES, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auditor_control_verdicts'
        unique_together = ('assessment', 'company_control')

    def is_reviewed(self):
        return self.status in self.REVIEWED_STATES


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
