from django.contrib import admin

from .models import MonitoringCheck, MonitoringRun, MonitoringFinding


@admin.register(MonitoringCheck)
class MonitoringCheckAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'check_type', 'frequency', 'status',
                    'last_result', 'last_run_at', 'next_run_at')
    list_filter = ('check_type', 'frequency', 'status', 'last_result')
    search_fields = ('title', 'description', 'company__name', 'company__name_ar')
    readonly_fields = ('last_run_at', 'next_run_at', 'last_result', 'created_at', 'updated_at')


@admin.register(MonitoringRun)
class MonitoringRunAdmin(admin.ModelAdmin):
    list_display = ('monitoring_check', 'company', 'status', 'summary', 'created_at')
    list_filter = ('status',)
    search_fields = ('summary', 'details', 'company__name')
    readonly_fields = ('created_at', 'started_at', 'finished_at')


@admin.register(MonitoringFinding)
class MonitoringFindingAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'severity', 'status', 'created_at')
    list_filter = ('severity', 'status')
    search_fields = ('title', 'description', 'company__name')
    readonly_fields = ('created_at', 'updated_at')
