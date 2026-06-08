from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('register/', views.register_company, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('account/delete/', views.delete_company_data, name='delete_company_data'),

    # Email verification (FR-002.8)
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),

    # MFA (FR-012.3)
    path('mfa/setup/', views.mfa_setup, name='mfa_setup'),
    path('mfa/challenge/', views.mfa_challenge, name='mfa_challenge'),

    # Password reset via email (FR-012.7) — Django built-in views
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='core/password_reset.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='core/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='core/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='core/password_reset_complete.html'), name='password_reset_complete'),
]
