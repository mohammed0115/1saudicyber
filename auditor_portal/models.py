"""
Auditor Portal Models - Audit sessions, notes, findings
"""
from django.db import models
from core.models import Company, User
from core.storage import private_media_storage  # P0-01: private attachment storage


class AuditorNote(models.Model):
    """Notes added by auditor during review."""
    assessment = models.ForeignKey('compliance.Assessment', on_delete=models.CASCADE, related_name='auditor_notes')
    company_control = models.ForeignKey('compliance.CompanyControl', on_delete=models.CASCADE, related_name='auditor_portal_notes')
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

    assessment = models.ForeignKey('compliance.Assessment', on_delete=models.CASCADE, related_name='document_requests')
    company_control = models.ForeignKey('compliance.CompanyControl', on_delete=models.CASCADE, related_name='document_requests')
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
    # Optional file the company attaches directly to its RFI response.
    # P0-01: private storage — never served via /media/; downloaded only through an authorized view.
    attachment = models.FileField(upload_to='rfi_responses/%Y/%m/', null=True, blank=True,
                                  storage=private_media_storage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_rfi_responses'
        ordering = ['-created_at']


class AuditorControlVerdict(models.Model):
    """The auditor's INTERNAL verdict for one control within an assessment.

    Internal readiness review only — never an official NCA/Aramco/SABIC certification.
    One current verdict per (assessment, company_control); updates overwrite in place.
    Every change is also appended to AuditorControlVerdictHistory for a full audit trail.
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
    # G1 — framework-native implementation/maturity level (feeds the domain compliance %).
    IMPLEMENTATION_CHOICES = [
        ('not_implemented', 'Not Implemented'),
        ('partially_implemented', 'Partially Implemented'),
        ('implemented', 'Implemented'),
        ('not_applicable', 'Not Applicable'),
    ]
    IMPLEMENTATION_AR = {
        'not_implemented': 'غير مطبّق', 'partially_implemented': 'مطبّق جزئيًا',
        'implemented': 'مطبّق', 'not_applicable': 'لا ينطبق',
    }
    # Weight for the maturity/compliance % (not_applicable is excluded from the denominator).
    IMPLEMENTATION_WEIGHT = {'implemented': 1.0, 'partially_implemented': 0.5, 'not_implemented': 0.0}
    # Statuses that count as a completed internal review of the control.
    REVIEWED_STATES = ('compliant', 'partially_compliant', 'non_compliant',
                       'needs_more_evidence', 'not_applicable')

    assessment = models.ForeignKey('compliance.Assessment', on_delete=models.CASCADE, related_name='control_verdicts')
    company_control = models.ForeignKey('compliance.CompanyControl', on_delete=models.CASCADE, related_name='auditor_verdicts')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='control_verdicts')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='not_reviewed')
    implementation_level = models.CharField(max_length=25, choices=IMPLEMENTATION_CHOICES, blank=True)
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

    @property
    def implementation_level_ar(self):
        return self.IMPLEMENTATION_AR.get(self.implementation_level, self.implementation_level)


class ReportImmutableError(Exception):
    """Raised on any attempt to modify or delete an already-issued AuditReport (P0-02)."""


class AuditReportQuerySet(models.QuerySet):
    """Application-level immutability backstop: bulk update()/delete() on issued reports are
    refused so a caller cannot bypass the model save()/delete() guards via a QuerySet. (This
    does not, and need not, stop a DBA acting directly on the database.)"""
    def update(self, **kwargs):
        raise ReportImmutableError('Issued audit reports cannot be bulk-updated.')

    def delete(self):
        raise ReportImmutableError('Issued audit reports cannot be bulk-deleted.')

    def _raw_delete(self, using):  # used by cascade collector — allow it (whole-assessment delete)
        return super()._raw_delete(using)


class AuditReport(models.Model):
    """Final INTERNAL audit report — WRITE-ONCE. One per assessment (OneToOne). Once issued it
    is immutable: save() refuses content changes and delete() is blocked (see below). It carries
    an integrity envelope (content_hash + assessment_status_at_issue + snapshot_version) so its
    provenance and contents are provable after the fact.
    """
    SNAPSHOT_VERSION = 1

    assessment = models.OneToOneField('compliance.Assessment', on_delete=models.CASCADE, related_name='final_report')
    # auditor == issued_by; submitted_at == issued_at.
    auditor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_reports')
    verdict = models.CharField(max_length=25, choices=[
        ('pass', 'Pass'), ('conditional_pass', 'Conditional Pass'), ('fail', 'Fail'),
    ])
    executive_summary = models.TextField()
    executive_summary_ar = models.TextField(blank=True)
    findings = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    # P0-02 integrity envelope.
    company_id_at_issue = models.PositiveIntegerField(null=True, blank=True)  # company identity, frozen
    scope_snapshot = models.JSONField(default=list)             # [{company_control_id, control_code, framework, applicability, verdict, verdict_at}]
    summary = models.JSONField(default=dict)                    # {scope_count, reviewed_count, compliant_count, ...}
    evidence_snapshot = models.JSONField(default=list)          # [{submission_id, filename, sha256, version, size}]
    assessment_status_at_issue = models.CharField(max_length=20, blank=True)
    snapshot_version = models.PositiveSmallIntegerField(default=SNAPSHOT_VERSION)
    content_hash = models.CharField(max_length=64, blank=True)  # sha256 of the issued content
    submitted_at = models.DateTimeField(auto_now_add=True)

    objects = AuditReportQuerySet.as_manager()

    class Meta:
        db_table = 'audit_reports'

    def compute_content_hash(self):
        """Canonical sha256 over the decision-bearing content + integrity envelope. JSON is
        serialized with sort_keys=True (key order never affects the hash) and a fixed UTF-8
        encoding; only the stable issue markers are included (issued_by + assessment_status_at_issue
        + snapshot_version), NOT the DB-assigned timestamp, so the hash is reproducible on verify."""
        import hashlib
        import json
        payload = json.dumps({
            'assessment': self.assessment_id, 'company': self.company_id_at_issue,
            'issued_by': self.auditor_id, 'verdict': self.verdict,
            'executive_summary': self.executive_summary, 'executive_summary_ar': self.executive_summary_ar,
            'findings': self.findings, 'recommendations': self.recommendations,
            'scope_snapshot': self.scope_snapshot, 'summary': self.summary,
            'evidence_snapshot': self.evidence_snapshot,
            'assessment_status_at_issue': self.assessment_status_at_issue,
            'snapshot_version': self.snapshot_version,
        }, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        """WRITE-ONCE: the initial create stamps content_hash; any later modification of an
        existing row is refused (ReportImmutableError). Model-level, not view-only — this also
        blocks admin edits, stray update_or_create update paths, and management commands."""
        if self.pk is not None and AuditReport.objects.filter(pk=self.pk).exists():
            raise ReportImmutableError(
                'An issued audit report is immutable and cannot be modified.')
        self.content_hash = self.compute_content_hash()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """A single-instance delete of an issued report is refused. (A cascade from deleting the
        parent Assessment is a bulk SQL delete and does not call this — that is the only removal
        path, and it removes the whole assessment, not just its report.)"""
        raise ReportImmutableError('An issued audit report cannot be deleted.')

    def verify_integrity(self):
        """True iff the stored content_hash still matches the current content."""
        return bool(self.content_hash) and self.content_hash == self.compute_content_hash()


class AuditFinding(models.Model):
    """G2 — a recorded non-conformity/observation from an auditor's control review.

    A verdict is the overall control decision; a FINDING is a specific gap with a
    severity that drives a corrective-action (CAPA) lifecycle. Internal readiness
    review only — never an official NCA/Aramco/SABIC certification.
    """
    SEVERITY_CHOICES = [
        ('major_nc', 'Major Non-Conformity'),
        ('minor_nc', 'Minor Non-Conformity'),
        ('observation', 'Observation'),
        ('ofi', 'Opportunity For Improvement'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_remediation', 'In Remediation'),
        ('reverify', 'Pending Re-verification'),
        ('closed', 'Closed'),
        ('reopened', 'Reopened'),
    ]
    OPEN_STATES = ('open', 'in_remediation', 'reverify', 'reopened')
    SEVERITY_AR = {'major_nc': 'عدم مطابقة رئيسي', 'minor_nc': 'عدم مطابقة ثانوي',
                   'observation': 'ملاحظة', 'ofi': 'فرصة تحسين'}
    STATUS_AR = {'open': 'مفتوح', 'in_remediation': 'قيد التصحيح', 'reverify': 'بانتظار إعادة التحقّق',
                 'closed': 'مُغلق', 'reopened': 'أُعيد فتحه'}

    assessment = models.ForeignKey('compliance.Assessment', on_delete=models.CASCADE, related_name='audit_findings')
    company_control = models.ForeignKey('compliance.CompanyControl', on_delete=models.CASCADE, related_name='audit_findings')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='raised_findings')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    root_cause = models.TextField(blank=True)
    evidence_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'audit_findings'
        ordering = ['-created_at']

    @property
    def severity_ar(self):
        return self.SEVERITY_AR.get(self.severity, self.severity)

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATES


class CorrectiveAction(models.Model):
    """G2 — a CAPA entry: how the company remediates a finding (owner + due date),
    and the auditor's re-verification outcome."""
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done (awaiting re-test)'),
        ('verified', 'Verified'),
    ]
    STATUS_AR = {'planned': 'مُخطّط', 'in_progress': 'قيد التنفيذ',
                 'done': 'مُنجز (بانتظار إعادة الاختبار)', 'verified': 'تم التحقّق'}

    finding = models.ForeignKey(AuditFinding, on_delete=models.CASCADE, related_name='corrective_actions')
    description = models.TextField()
    owner = models.CharField(max_length=160, blank=True)   # company-side responsible party
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    verification_note = models.TextField(blank=True)       # auditor re-test note
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='corrective_actions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'corrective_actions'
        ordering = ['due_date', 'created_at']

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)


class CompanyMessage(models.Model):
    """G5 — lightweight in-app message on a company's engagement thread.

    Participants (enforced in the view via messaging.can_access_thread): the company's
    own users, its ACCEPTED assigned auditor(s), and platform staff. Internal
    communication only — not an official record or certification artefact.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='thread_messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='sent_thread_messages')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_messages'
        ordering = ['created_at']


class AuditorControlVerdictHistory(models.Model):
    """Append-only audit trail of every internal verdict recorded on a control.

    AuditorControlVerdict holds the CURRENT verdict (overwritten in place on each
    save). This model preserves the FULL history — every change, who made it, when —
    so a past internal verdict is defensible and reproducible. Never edited/deleted.
    """
    assessment = models.ForeignKey('compliance.Assessment', on_delete=models.CASCADE,
                                   related_name='verdict_history')
    company_control = models.ForeignKey('compliance.CompanyControl', on_delete=models.CASCADE,
                                        related_name='verdict_history')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='verdict_history_entries')
    status = models.CharField(max_length=25)
    implementation_level = models.CharField(max_length=25, blank=True)
    impact = models.CharField(max_length=20, blank=True)
    rationale = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auditor_control_verdict_history'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['assessment', 'company_control'])]

    def __str__(self):
        return f"{self.company_control_id}:{self.status}@{self.created_at:%Y-%m-%d}"
