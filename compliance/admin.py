from django.contrib import admin
from .models import Framework, Domain, Control, CompanyControl, Evidence, ControlMapping


@admin.register(Framework)
class FrameworkAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'version']


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ['name', 'framework', 'order']
    list_filter = ['framework']


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):
    list_display = ['control_id', 'title', 'framework', 'domain', 'priority']
    list_filter = ['framework', 'domain', 'priority']
    search_fields = ['control_id', 'title']


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
