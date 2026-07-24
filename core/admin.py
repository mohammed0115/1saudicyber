from django.contrib import admin, messages
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

    # P0-02: never let the admin cascade an issued audit report away by deleting a company.
    # The model-level Company.delete()/CompanyQuerySet.delete() guards are the hard backstop;
    # these give the admin a clean, informative experience instead of an error page.
    @staticmethod
    def _has_issued_report(company):
        from core.models import _company_has_issued_report
        return company is not None and _company_has_issued_report([company.pk])

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self._has_issued_report(obj):
            return False   # hides the single-object delete button for protected companies
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        if self._has_issued_report(obj):
            self.message_user(request, 'لا يمكن حذف شركة تملك تقرير تدقيق نهائيًا صادرًا — يجب أرشفتها.',
                              level=messages.ERROR)
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from core.models import _company_has_issued_report
        protected = [c.pk for c in queryset if _company_has_issued_report([c.pk])]
        if protected:
            self.message_user(request, 'تم إلغاء الحذف: %d شركة تملك تقارير تدقيق نهائية صادرة يجب '
                              'الاحتفاظ بها.' % len(protected), level=messages.ERROR)
            return
        super().delete_queryset(request, queryset)
