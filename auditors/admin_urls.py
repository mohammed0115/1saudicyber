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
    path('companies/<int:company_id>/link-user/', admin_views.crm_link_user, name='link_user'),
    path('companies/<int:company_id>/unlink-user/', admin_views.crm_unlink_user, name='unlink_user'),
    path('companies/<int:company_id>/add-note/', admin_views.crm_add_note, name='add_note'),
    path('companies/<int:company_id>/update-status/', admin_views.crm_update_status, name='update_status'),
    path('companies/<int:company_id>/subscription-action/', admin_views.crm_subscription_action, name='subscription_action'),
    path('companies/<int:company_id>/payments/manual/add/', admin_views.crm_add_manual_payment, name='add_manual_payment'),
    path('companies/<int:company_id>/payments/<int:payment_id>/confirm/', admin_views.crm_confirm_manual_payment, name='confirm_manual_payment'),
    path('companies/<int:company_id>/payments/<int:payment_id>/reject/', admin_views.crm_reject_manual_payment, name='reject_manual_payment'),
    path('unlinked-accounts/', admin_views.crm_unlinked_accounts, name='unlinked_accounts'),

    # Auditor approval (Phase 8D-3A)
    path('auditors/', admin_views.auditor_approval_list, name='auditor_list'),
    path('auditors/<int:profile_id>/', admin_views.auditor_approval_detail, name='auditor_detail'),
    path('auditors/<int:profile_id>/action/', admin_views.auditor_approval_action, name='auditor_action'),
]
