from django.contrib import admin

from .models import RiskItem, RemediationTask


@admin.register(RiskItem)
class RiskItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'severity', 'status', 'category',
                    'inherent_score', 'due_date', 'owner_name', 'updated_at')
    list_filter = ('severity', 'status', 'category', 'source')
    search_fields = ('title', 'description', 'owner_name', 'company__name', 'company__name_ar')
    readonly_fields = ('inherent_score', 'residual_score', 'severity', 'created_at', 'updated_at')


@admin.register(RemediationTask)
class RemediationTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'risk', 'status', 'priority', 'due_date', 'owner_name')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'description', 'owner_name', 'company__name')
    readonly_fields = ('completed_at', 'created_at', 'updated_at')
