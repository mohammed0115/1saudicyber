from django.contrib import admin
from .models import (
    Framework, Domain, Control, CompanyControl, Evidence, ControlMapping,
    SourceDocument, FrameworkVersion, ControlVersion, ControlApplicabilityTag,
    CompanyIntakeProfile, FrameworkApplicabilityResult,
    CompanyFrameworkScope, ControlApplicabilityResult,
    EvidenceRequirement, EvidenceChecklistItem,
)


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
    search_fields = ['control_id', 'title', 'external_reference', 'source_reference']


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
