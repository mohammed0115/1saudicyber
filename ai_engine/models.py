"""
AI Engine Models - Classification results, audit logs
"""
from django.db import models
from core.models import Company


class AIClassificationLog(models.Model):
    """Log of AI classification decisions."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='classification_logs')
    input_data = models.JSONField(default=dict)
    output_data = models.JSONField(default=dict)
    model_used = models.CharField(max_length=50)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    processing_time_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_classification_logs'


class AIAuditLog(models.Model):
    """Log of AI evidence analysis decisions."""
    evidence_id = models.IntegerField()
    control_id = models.CharField(max_length=50)
    company_name = models.CharField(max_length=255)
    input_text = models.TextField(blank=True)
    verdict = models.CharField(max_length=25)
    confidence = models.FloatField(default=0.0)
    reasoning = models.TextField(blank=True)
    reasoning_ar = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    recommendations_ar = models.TextField(blank=True)
    model_used = models.CharField(max_length=50)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    processing_time_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_audit_logs'


class GapAnalysis(models.Model):
    """AI-generated gap analysis for a company."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gap_analyses')
    framework_code = models.CharField(max_length=50)
    total_controls = models.IntegerField(default=0)
    compliant_count = models.IntegerField(default=0)
    non_compliant_count = models.IntegerField(default=0)
    partially_compliant_count = models.IntegerField(default=0)
    not_assessed_count = models.IntegerField(default=0)
    compliance_score = models.FloatField(default=0.0)
    risk_score = models.FloatField(default=0.0)
    high_risk_gaps = models.JSONField(default=list)
    remediation_priorities = models.JSONField(default=list)
    ai_prediction = models.TextField(blank=True)
    ai_prediction_ar = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gap_analyses'

    def __str__(self):
        return f"{self.company.name} - {self.framework_code}: {self.compliance_score}%"


class PromptTemplate(models.Model):
    """Source-controlled prompt metadata for reproducible model requests."""

    key = models.SlugField(max_length=100)
    version = models.CharField(max_length=40)
    purpose = models.CharField(max_length=100)
    template = models.TextField()
    output_schema = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_prompt_templates'
        constraints = [
            models.UniqueConstraint(fields=['key', 'version'], name='unique_ai_prompt_template_version'),
        ]


class ModelProfile(models.Model):
    """An approved model/provider routing profile; it never stores provider secrets."""

    key = models.SlugField(max_length=100, unique=True)
    provider = models.CharField(max_length=50, default='openai')
    model_name = models.CharField(max_length=100)
    credential_reference = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_model_profiles'


class EvidenceChunk(models.Model):
    """Traceable evidence segment used to ground an AI decision."""

    evidence = models.ForeignKey('compliance.Evidence', on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    content_hash = models.CharField(max_length=64, db_index=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'evidence_chunks'
        constraints = [
            models.UniqueConstraint(fields=['evidence', 'chunk_index'], name='unique_evidence_chunk_index'),
        ]
        ordering = ['chunk_index']


class AIDecisionRecord(models.Model):
    """A governance record that joins model, prompt, policy, evidence citations, and review state."""

    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('review_required', 'Review required'),
        ('rejected', 'Rejected'),
        ('error', 'Error'),
    ]

    evidence = models.ForeignKey('compliance.Evidence', on_delete=models.CASCADE, related_name='decision_records')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ai_decision_records')
    control = models.ForeignKey('compliance.Control', on_delete=models.PROTECT, related_name='ai_decision_records')
    model_profile = models.ForeignKey(ModelProfile, null=True, blank=True, on_delete=models.SET_NULL)
    model_name = models.CharField(max_length=100)
    prompt_key = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=40)
    policy_version_reference = models.CharField(max_length=100, blank=True)
    input_hash = models.CharField(max_length=64, db_index=True)
    output_payload = models.JSONField(default=dict)
    output_hash = models.CharField(max_length=64, db_index=True)
    cited_chunk_indexes = models.JSONField(default=list)
    confidence = models.FloatField(default=0.0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES)
    human_reviewed_by = models.ForeignKey(
        'core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_ai_decisions',
    )
    human_reviewed_at = models.DateTimeField(null=True, blank=True)
    trace_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_decision_records'
        ordering = ['-created_at']
