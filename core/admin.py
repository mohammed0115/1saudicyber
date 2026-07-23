from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Company

# ---- PILOT-HOTFIX-B (A) — Django admin branding: Get Solution Company / 1SaudiCyber ----
admin.site.site_header = "Get Solution Company — 1SaudiCyber Admin"
admin.site.site_title = "Get Solution Company"
admin.site.index_title = "1SaudiCyber Operations Administration"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Safe custom-user admin.

    Uses Django's ``UserChangeForm`` (via ``DjangoUserAdmin``), so the password is
    shown through a ``ReadOnlyPasswordHashField`` with the standard "change password"
    link — never as a raw editable text field. ``mfa_secret`` (TOTP secret) is
    intentionally excluded from every fieldset so it is never displayed or editable.
    """
    list_display = ['email', 'first_name', 'last_name', 'role', 'company', 'is_staff', 'is_active']
    list_filter = ['role', 'is_staff', 'is_superuser', 'is_active', 'company']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['email']
    # Technical/security fields are read-only; secrets are excluded entirely.
    readonly_fields = ['last_login', 'date_joined', 'email_verified', 'mfa_enabled']
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Role & tenant', {'fields': ('role', 'company')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser',
                                    'groups', 'user_permissions')}),
        ('Security (read-only)', {'fields': ('email_verified', 'mfa_enabled',
                                             'last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',),
                'fields': ('email', 'username', 'password1', 'password2', 'role', 'company')}),
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'cr_number', 'sector', 'size', 'risk_level', 'status', 'created_at']
    list_filter = ['sector', 'size', 'risk_level', 'status', 'target_nca', 'target_aramco', 'target_sabic']
    search_fields = ['name', 'name_ar', 'cr_number', 'contact_email']
    # P0-02: `status` is product-driven (classification / assignment flow) and, crucially, there
    # is NO official certification process — so it must not be hand-editable to 'certified' via
    # the admin. Read-only here until a real accreditation workflow exists.
    readonly_fields = ['status', 'created_at', 'updated_at', 'classification_date']
