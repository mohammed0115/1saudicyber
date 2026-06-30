"""Get Solution platform-admin routes.

Phase 8D-3A — auditor approval.
Phase 8D-3B-ADMIN-CRM-A — read-only CRM console (dashboard, companies, unlinked accounts).
"""
from django.urls import path

from . import admin_views

app_name = 'platform_admin'

urlpatterns = [
    # CRM console (read-only foundation)
    path('', admin_views.crm_dashboard, name='dashboard'),
    path('companies/', admin_views.crm_companies_list, name='companies_list'),
    path('companies/<int:company_id>/', admin_views.crm_company_detail, name='company_detail'),
    path('unlinked-accounts/', admin_views.crm_unlinked_accounts, name='unlinked_accounts'),

    # Auditor approval (Phase 8D-3A)
    path('auditors/', admin_views.auditor_approval_list, name='auditor_list'),
    path('auditors/<int:profile_id>/', admin_views.auditor_approval_detail, name='auditor_detail'),
    path('auditors/<int:profile_id>/action/', admin_views.auditor_approval_action, name='auditor_action'),
]
