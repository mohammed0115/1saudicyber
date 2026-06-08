"""
Compliance Models - Frameworks, Controls, Evidence, Assessments
"""
from django.db import models
from core.models import Company, User


class Framework(models.Model):
    """Compliance framework (NCA ECC, Aramco SACS-002, SABIC CyberTrust)."""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=20, blank=True)
    total_controls = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'frameworks'

    def __str__(self):
        return self.name


class Domain(models.Model):
    """Control domain/category within a framework."""
    framework = models.ForeignKey(Framework, on_delete=models.CASCADE, related_name='domains')
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'domains'
        ordering = ['order']

    def __str__(self):
        return f"{self.framework.code} - {self.name}"


class Control(models.Model):
    """Individual compliance control/requirement."""
    PRIORITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    EVIDENCE_TYPE_CHOICES = [
        ('policy', 'Policy Document'),
        ('procedure', 'Procedure Document'),
        ('screenshot', 'System Screenshot'),
        ('config', 'Configuration Export'),
        ('report', 'Audit/Scan Report'),
        ('log', 'System Log'),
        ('interview', 'Interview Record'),
        ('certificate', 'Certificate/License'),
        ('other', 'Other'),
    ]

    framework = models.ForeignKey(Framework, on_delete=models.CASCADE, related_name='controls')
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name='controls')
    control_id = models.CharField(max_length=50)
    title = models.CharField(max_length=500)
    title_ar = models.CharField(max_length=500, blank=True)
    description = models.TextField()
    description_ar = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPE_CHOICES, default='policy')
    evidence_guidance = models.TextField(blank=True)
    evidence_guidance_ar = models.TextField(blank=True)

    # Cross-mapping
    mapped_controls = models.ManyToManyField('self', blank=True, symmetrical=True)

    # Applicability
    applies_to_sectors = models.JSONField(default=list, blank=True)
    applies_to_sizes = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        db_table = 'controls'
        unique_together = ['framework', 'control_id']

    def __str__(self):
        return f"{self.control_id}: {self.title[:60]}"


class CompanyControl(models.Model):
    """Tracks a company's compliance status for each applicable control."""
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('evidence_uploaded', 'Evidence Uploaded'),
        ('ai_reviewed', 'AI Reviewed'),
        ('compliant', 'Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('not_applicable', 'Not Applicable'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_controls')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='company_controls')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='not_started')
    ai_verdict = models.CharField(max_length=25, blank=True)
    ai_confidence = models.FloatField(default=0.0)
    ai_reasoning = models.TextField(blank=True)
    ai_reasoning_ar = models.TextField(blank=True)
    ai_recommendations = models.TextField(blank=True)
    ai_recommendations_ar = models.TextField(blank=True)
    auditor_verdict = models.CharField(max_length=25, blank=True)
    auditor_notes = models.TextField(blank=True)
    last_assessed = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_controls'
        unique_together = ['company', 'control']

    def __str__(self):
        return f"{self.company.name} - {self.control.control_id}: {self.status}"


class Evidence(models.Model):
    """Uploaded evidence document for a specific control."""
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing (OCR)'),
        ('ai_analyzing', 'AI Analyzing'),
        ('reviewed', 'AI Reviewed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]

    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='evidences')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to='evidence/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.IntegerField(default=0)

    # OCR extracted text
    extracted_text = models.TextField(blank=True)
    ocr_confidence = models.FloatField(default=0.0)
    ocr_language = models.CharField(max_length=10, blank=True)

    # AI Analysis
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    ai_analysis = models.JSONField(default=dict, blank=True)
    ai_verdict = models.CharField(max_length=25, blank=True)
    ai_reasoning = models.TextField(blank=True)
    ai_reasoning_ar = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'evidences'

    def __str__(self):
        return f"{self.original_filename} ({self.status})"


class Assessment(models.Model):
    """Full compliance assessment/audit session for a company."""
    TYPE_CHOICES = [
        ('self_assessment', 'Self Assessment'),
        ('ai_assessment', 'AI Assessment'),
        ('formal_audit', 'Formal Audit'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('ai_complete', 'AI Review Complete'),
        ('auditor_review', 'Auditor Review'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='assessments')
    assessment_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    frameworks = models.ManyToManyField(Framework, related_name='assessments')
    assigned_auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_assessments')

    overall_score = models.FloatField(default=0.0)
    nca_score = models.FloatField(default=0.0)
    aramco_score = models.FloatField(default=0.0)
    sabic_score = models.FloatField(default=0.0)

    total_controls = models.IntegerField(default=0)
    compliant_controls = models.IntegerField(default=0)
    non_compliant_controls = models.IntegerField(default=0)
    partially_compliant_controls = models.IntegerField(default=0)

    ai_summary = models.TextField(blank=True)
    ai_summary_ar = models.TextField(blank=True)
    auditor_report = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assessments'

    def __str__(self):
        return f"{self.company.name} - {self.assessment_type} ({self.status})"


class ControlMapping(models.Model):
    """Cross-mapping between controls from different frameworks."""
    MAPPING_TYPE_CHOICES = [
        ('equivalent', 'Equivalent'),
        ('partial', 'Partial'),
        ('related', 'Related'),
    ]

    source_control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='source_mappings')
    target_control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='target_mappings')
    mapping_type = models.CharField(max_length=20, choices=MAPPING_TYPE_CHOICES, default='equivalent')
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'control_mappings'
        unique_together = ['source_control', 'target_control']

    def __str__(self):
        return f"{self.source_control.control_id} -> {self.target_control.control_id} ({self.mapping_type})"
