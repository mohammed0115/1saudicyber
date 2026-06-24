from django.contrib import admin

from .models import AuditorProfile, AuditorAssignment


@admin.register(AuditorProfile)
class AuditorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'status', 'is_available', 'city', 'organization_name', 'updated_at')
    list_filter = ('status', 'is_available', 'city')
    search_fields = ('full_name', 'user__email', 'organization_name', 'specialization')
    list_editable = ('status', 'is_available')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuditorAssignment)
class AuditorAssignmentAdmin(admin.ModelAdmin):
    list_display = ('company', 'auditor', 'status', 'scope', 'requested_by', 'requested_at')
    list_filter = ('status', 'scope')
    search_fields = ('company__name', 'company__name_ar', 'auditor__full_name')
    readonly_fields = ('requested_at', 'created_at', 'updated_at')
