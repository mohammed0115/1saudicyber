"""Phase 8D-3A — Get Solution platform-admin auditor approval routes."""
from django.urls import path

from . import admin_views

app_name = 'platform_admin'

urlpatterns = [
    path('auditors/', admin_views.auditor_approval_list, name='auditor_list'),
    path('auditors/<int:profile_id>/', admin_views.auditor_approval_detail, name='auditor_detail'),
    path('auditors/<int:profile_id>/action/', admin_views.auditor_approval_action, name='auditor_action'),
]
