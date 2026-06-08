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
