from django.contrib import admin
from .models import (
    Framework, Domain, Control, CompanyControl, Evidence, ControlMapping,
    SourceDocument, FrameworkVersion, ControlVersion, ControlApplicabilityTag,
    CompanyIntakeProfile, FrameworkApplicabilityResult,
    CompanyFrameworkScope, ControlApplicabilityResult,
    EvidenceRequirement, EvidenceChecklistItem, EvidenceSubmission, EvidenceAnalysisResult,
    ControlAssessment, EvidenceTextExtraction, EvidenceAIAnalysis, EvidenceRuleEvaluation,
    AuditorFinalVerdict, ControlGapAssessment,
)


@admin.register(ControlGapAssessment)
class ControlGapAssessmentAdmin(admin.ModelAdmin):
    """Deterministic preliminary readiness per control (always requires human review)."""
    list_display = ['company', 'control', 'framework_version', 'status', 'score', 'evidence_count']
    list_filter = ['status', 'framework_version']
    search_fields = ['company__name', 'control__control_id']


@admin.register(EvidenceTextExtraction)
class EvidenceTextExtractionAdmin(admin.ModelAdmin):
    """Read-only: extraction is computed by the service, never edited by hand."""
    list_display = ('submission', 'status', 'char_count', 'page_count', 'extraction_method', 'extracted_at')
    list_filter = ('status', 'extraction_method')
    search_fields = ('submission__original_filename',)
    readonly_fields = ('submission', 'status', 'extracted_text', 'char_count', 'page_count',
                       'extraction_method', 'warnings', 'error_message', 'truncated', 'extracted_at')

    def has_add_permission(self, request):
        return False


@admin.register(EvidenceAIAnalysis)
class EvidenceAIAnalysisAdmin(admin.ModelAdmin):
    """Read-only: advisory AI analysis is produced by the service, never hand-edited."""
    list_display = ('submission', 'status', 'relevance', 'confidence', 'analyzed_at')
    list_filter = ('status', 'relevance')
    search_fields = ('submission__original_filename',)
    readonly_fields = ('submission', 'status', 'relevance', 'confidence', 'summary',
                       'matched_signals', 'missing_items', 'recommendations', 'raw_response',
                       'error_message', 'analyzed_at')

    def has_add_permission(self, request):
        return False


@admin.register(EvidenceRuleEvaluation)
class EvidenceRuleEvaluationAdmin(admin.ModelAdmin):
    """Read-only: suggested status is computed by the rule engine, never hand-edited."""
    list_display = ('submission', 'status', 'suggested_status', 'confidence', 'framework_type', 'evaluated_at')
    list_filter = ('status', 'suggested_status', 'framework_type')
    search_fields = ('submission__original_filename',)
    readonly_fields = ('submission', 'status', 'suggested_status', 'confidence', 'rationale',
                       'rule_signals', 'missing_requirements', 'framework_type', 'error_message',
                       'evaluated_at')

    def has_add_permission(self, request):
        return False


@admin.register(AuditorFinalVerdict)
class AuditorFinalVerdictAdmin(admin.ModelAdmin):
    """Read-only audit view: verdicts are recorded via the review workflow, not the admin."""
    list_display = ('submission', 'status', 'reviewer', 'confidence', 'framework_type', 'reviewed_at')
    list_filter = ('status', 'framework_type')
    search_fields = ('submission__original_filename', 'reviewer__email')
    readonly_fields = ('submission', 'reviewer', 'status', 'confidence', 'rationale',
                       'required_actions', 'framework_type', 'source_rule_evaluation', 'reviewed_at')

    def has_add_permission(self, request):
        return False


@admin.register(Framework)
class FrameworkAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'version']


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ['name', 'framework', 'order']
    list_filter = ['framework']


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):
    list_display = ['control_id', 'title', 'framework', 'framework_version', 'domain',
                    'priority', 'is_legacy_import']
    list_filter = ['framework', 'framework_version', 'domain', 'priority', 'is_legacy_import']
    search_fields = ['control_id', 'title', 'external_reference', 'source_reference',
                     'framework_version__code', 'framework__code', 'domain__name']


@admin.register(CompanyControl)
class CompanyControlAdmin(admin.ModelAdmin):
    list_display = ['company', 'control', 'status', 'ai_verdict', 'ai_confidence']
    list_filter = ['status', 'ai_verdict', 'company']


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ['company_control', 'original_filename', 'ai_verdict', 'uploaded_at']
    list_filter = ['ai_verdict']


@admin.register(ControlMapping)
class ControlMappingAdmin(admin.ModelAdmin):
    list_display = ['source_control', 'target_control', 'mapping_type']


# ---- Phase 1: Source Registry + Framework Versioning ----

@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'issuer', 'document_type', 'version', 'status', 'is_current']
    list_filter = ['issuer', 'document_type', 'status', 'language', 'is_current']
    search_fields = ['title', 'version', 'notes']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(FrameworkVersion)
class FrameworkVersionAdmin(admin.ModelAdmin):
    list_display = ['code', 'framework', 'version_label', 'status', 'is_default', 'source_document']
    list_filter = ['status', 'is_default', 'framework']
    search_fields = ['code', 'version_label', 'notes']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ControlVersion)
class ControlVersionAdmin(admin.ModelAdmin):
    list_display = ['control', 'version_label', 'framework_version', 'effective_date', 'retired_date']
    list_filter = ['framework_version', 'source_document']
    search_fields = ['control__control_id', 'version_label', 'control_id_snapshot', 'title_snapshot']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ControlApplicabilityTag)
class ControlApplicabilityTagAdmin(admin.ModelAdmin):
    list_display = ['control', 'tag', 'source']
    list_filter = ['tag', 'source']
    search_fields = ['control__control_id', 'tag', 'notes']
    readonly_fields = ['created_at', 'updated_at']


# ---- Phase 3A: Company Intake + Framework Applicability ----

@admin.register(CompanyIntakeProfile)
class CompanyIntakeProfileAdmin(admin.ModelAdmin):
    list_display = ['company', 'review_status', 'works_with_aramco', 'works_with_sabic',
                    'is_government_entity', 'is_critical_system_operator', 'uses_cloud_services']
    list_filter = ['review_status', 'works_with_aramco', 'works_with_sabic',
                   'is_government_entity', 'is_critical_system_operator']
    search_fields = ['company__name', 'notes']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(FrameworkApplicabilityResult)
class FrameworkApplicabilityResultAdmin(admin.ModelAdmin):
    list_display = ['company', 'framework_version', 'decision', 'source', 'confidence']
    list_filter = ['decision', 'source', 'framework_version']
    search_fields = ['company__name', 'framework_version__code', 'reason', 'override_reason']
    readonly_fields = ['created_at', 'updated_at']


# ---- Phase 3C: Framework Scope + Control Applicability planning ----

@admin.register(CompanyFrameworkScope)
class CompanyFrameworkScopeAdmin(admin.ModelAdmin):
    list_display = ['company', 'framework_version', 'status', 'source', 'approved_by', 'approved_at']
    list_filter = ['status', 'source', 'framework_version']
    search_fields = ['company__name', 'framework_version__code', 'reason', 'rejection_reason']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ControlApplicabilityResult)
class ControlApplicabilityResultAdmin(admin.ModelAdmin):
    list_display = ['company', 'control', 'decision', 'source', 'confidence']
    list_filter = ['decision', 'source', 'framework_scope__framework_version']
    search_fields = ['company__name', 'control__control_id', 'control__title', 'reason']
    readonly_fields = ['created_at', 'updated_at']


# ---- Phase 3D: Evidence Requirement templates + checklist planning ----

@admin.register(EvidenceRequirement)
class EvidenceRequirementAdmin(admin.ModelAdmin):
    list_display = ['control', 'title', 'evidence_type', 'requirement_level', 'source', 'is_active']
    list_filter = ['evidence_type', 'requirement_level', 'source', 'is_active']
    search_fields = ['control__control_id', 'title', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(EvidenceChecklistItem)
class EvidenceChecklistItemAdmin(admin.ModelAdmin):
    list_display = ['company', 'evidence_requirement', 'status', 'priority', 'due_date', 'assigned_to']
    list_filter = ['status', 'priority']
    search_fields = ['company__name', 'evidence_requirement__title', 'evidence_requirement__control__control_id']
    readonly_fields = ['created_at', 'updated_at']


# ---- Phase 3E: Evidence Upload v2 submissions ----

@admin.register(EvidenceSubmission)
class EvidenceSubmissionAdmin(admin.ModelAdmin):
    list_display = ['company', 'original_filename', 'file_type', 'version', 'status', 'uploaded_at']
    list_filter = ['status', 'file_type', 'company']
    search_fields = ['original_filename', 'company__name',
                     'checklist_item__evidence_requirement__control__control_id']
    readonly_fields = ['uploaded_at', 'file_hash', 'file_size', 'created_at', 'updated_at']


# ---- Phase 3F: advisory evidence analysis ----

@admin.register(EvidenceAnalysisResult)
class EvidenceAnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['company', 'evidence_submission', 'control', 'status', 'confidence', 'provider', 'created_at']
    list_filter = ['status', 'provider', 'company']
    search_fields = ['company__name', 'control__control_id', 'evidence_submission__original_filename', 'summary']
    readonly_fields = ['created_at', 'updated_at', 'extracted_text', 'model_used', 'provider', 'analysis_metadata']


# ---- Phase 3G: Auditor control assessment ----

@admin.register(ControlAssessment)
class ControlAssessmentAdmin(admin.ModelAdmin):
    list_display = ['company', 'control', 'status', 'risk_level', 'remediation_required', 'reviewed_by', 'reviewed_at']
    list_filter = ['status', 'risk_level', 'remediation_required', 'company']
    search_fields = ['company__name', 'control__control_id', 'control__title', 'auditor_notes']
    readonly_fields = ['created_at', 'updated_at', 'ai_summary_snapshot']
