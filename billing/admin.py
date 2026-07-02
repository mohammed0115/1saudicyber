from django.contrib import admin

from .models import CompanySubscription, Plan, Payment


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'status', 'plan_name', 'plan', 'provider', 'starts_at', 'ends_at',
                    'report_exports_allowed', 'updated_at')
    list_filter = ('status', 'provider', 'report_exports_allowed', 'auditor_assignment_allowed')
    search_fields = ('company__name', 'company__name_ar', 'plan_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'price_amount', 'currency', 'billing_cycle', 'is_active', 'sort_order')
    list_filter = ('is_active', 'billing_cycle')
    search_fields = ('code', 'name')
    list_editable = ('price_amount', 'is_active', 'sort_order')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('company', 'amount', 'currency', 'provider', 'status', 'reference', 'created_at')
    list_filter = ('provider', 'status', 'currency')
    search_fields = ('company__name', 'reference', 'provider_payment_id')
    readonly_fields = ('created_at', 'updated_at')
