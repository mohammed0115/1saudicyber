from django.contrib import admin

from .models import CompanySubscription


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'status', 'plan_name', 'starts_at', 'ends_at',
                    'report_exports_allowed', 'updated_at')
    list_filter = ('status', 'report_exports_allowed', 'auditor_assignment_allowed')
    search_fields = ('company__name', 'company__name_ar', 'plan_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ()
