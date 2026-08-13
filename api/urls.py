"""/api/v1 URL routes (SRS Appendix D)."""
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import platform_views, views

app_name = 'api'

urlpatterns = [
    path('health/', platform_views.health, name='health'),
    path('platform/capabilities/', platform_views.platform_capabilities, name='platform-capabilities'),
    path('platform/openapi/', platform_views.openapi_contract, name='platform-openapi'),
    path('register/', views.register, name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'),          # JWT (NFR-013)
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('classify/', views.classify, name='classify'),
    path('controls/', views.controls, name='controls'),
    path('controls/<int:control_id>/', views.control_detail, name='control_detail'),
    path('evidence/upload/', views.evidence_upload, name='evidence_upload'),
    path('evidence/<int:evidence_id>/analyze/', views.evidence_analyze, name='evidence_analyze'),
    path('gap-analysis/', views.gap_analysis, name='gap_analysis'),
    path('dashboard/executive/', views.dashboard_executive, name='dashboard_executive'),
    path('dashboard/compliance/', views.dashboard_compliance, name='dashboard_compliance'),
    path('monitoring/scores/', views.monitoring_scores, name='monitoring_scores'),
    path('monitoring/alerts/', views.monitoring_alerts, name='monitoring_alerts'),
    path('auditor/assignments/', views.auditor_assignments, name='auditor_assignments'),
    path('platform/', include('policy_engine.urls')),
    path('platform/', include('integrations.urls')),
    path('platform/', include('platform_events.urls')),
]
