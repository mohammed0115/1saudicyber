from django.contrib import admin
from .models import User, Company


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'company', 'is_active']
    list_filter = ['role', 'is_active', 'company']
    search_fields = ['email', 'first_name', 'last_name']


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'cr_number', 'sector', 'size', 'risk_level', 'created_at']
    list_filter = ['sector', 'size', 'risk_level', 'target_nca', 'target_aramco', 'target_sabic']
    search_fields = ['name', 'cr_number']
