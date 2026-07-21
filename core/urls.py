from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('register/', views.register_company, name='register'),

    # Phase 4A — self-service registration + onboarding (additive; legacy register/ kept)
    path('get-started/', views.get_started, name='get_started'),
    path('get-started/company/', views.company_self_register, name='company_register'),
    path('get-started/auditor/', views.auditor_interest, name='auditor_register'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('onboarding/complete/', views.onboarding_complete, name='onboarding_complete'),
    path('onboarding/resend-verification/', views.resend_verification_link, name='resend_verification_link'),

    # Phase 8D-2-FIX-A — public legal pages
    path('privacy/', views.privacy_policy, name='privacy'),
    path('terms/', views.terms_of_use, name='terms'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('account/delete/', views.delete_company_data, name='delete_company_data'),

    # Phase 8D-3B-AUTH-A — 6-digit email OTP verification (static routes BEFORE the
    # token route so 'resend' is never captured as a verification token).
    path('verify-email/', views.verify_email_otp, name='verify_email_otp'),
    path('verify-email/resend/', views.resend_email_otp, name='resend_email_otp'),

    # Email verification (FR-002.8) — legacy one-time link
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),

    # MFA (FR-012.3)
    path('mfa/setup/', views.mfa_setup, name='mfa_setup'),
    path('mfa/challenge/', views.mfa_challenge, name='mfa_challenge'),

    # Password reset via email (FR-012.7) — Django built-in views.
    # Namespaced success_url is set explicitly so reverse() resolves under 'core:'.
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='core/password_reset.html',
        email_template_name='core/password_reset_email.txt',
        subject_template_name='core/password_reset_subject.txt',
        success_url=reverse_lazy('core:password_reset_done')), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='core/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='core/password_reset_confirm.html',
        success_url=reverse_lazy('core:password_reset_complete')), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='core/password_reset_complete.html'), name='password_reset_complete'),

    # DD-fix (commercial) — team invites / user management
    path('team/', views.team_view, name='team'),
    path('settings/', views.settings_hub, name='settings'),
    path('notifications/', views.notifications_inbox, name='notifications_inbox'),
    path('notifications/<int:note_id>/open/', views.notification_open, name='notification_open'),
    path('invite/<str:token>/', views.accept_invite_view, name='accept_invite'),
]
