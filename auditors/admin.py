from django.contrib import admin

from .models import AuditorProfile, AuditorAssignment
from . import admin_services as svc


@admin.register(AuditorProfile)
class AuditorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'status', 'is_available', 'city', 'organization_name', 'updated_at')
    list_filter = ('status', 'is_available', 'city')
    search_fields = ('full_name', 'user__email', 'organization_name', 'specialization')
    list_editable = ('status', 'is_available')
    readonly_fields = ('created_at', 'updated_at')
    # Get Solution platform-admin bulk actions (reason-free transitions only;
    # reject/suspend require a reason and are done via /platform-admin/auditors/).
    actions = ('admin_approve_selected', 'admin_reactivate_selected')

    @admin.action(description='اعتماد وتفعيل المدققين المحددين (Get Solution)')
    def admin_approve_selected(self, request, queryset):
        done = 0
        for profile in queryset:
            try:
                svc.apply_auditor_action(profile, 'approve', request.user)
                done += 1
            except svc.AuditorAdminError:
                continue
        self.message_user(request, f'تم تفعيل {done} مدقق.')

    @admin.action(description='إعادة تفعيل المدققين المحددين (Get Solution)')
    def admin_reactivate_selected(self, request, queryset):
        done = 0
        for profile in queryset:
            try:
                svc.apply_auditor_action(profile, 'reactivate', request.user)
                done += 1
            except svc.AuditorAdminError:
                continue
        self.message_user(request, f'تم إعادة تفعيل {done} مدقق.')


@admin.register(AuditorAssignment)
class AuditorAssignmentAdmin(admin.ModelAdmin):
    list_display = ('company', 'auditor', 'status', 'scope', 'requested_by', 'requested_at')
    list_filter = ('status', 'scope')
    search_fields = ('company__name', 'company__name_ar', 'auditor__full_name')
    readonly_fields = ('requested_at', 'created_at', 'updated_at')
