"""/api/v1 URL routes (SRS Appendix D)."""
from django.urls import path
from .authentication import VerifiedTokenObtainPairView, VerifiedTokenRefreshView
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)

from . import views

app_name = 'api'

urlpatterns = [
    # Auto-generated OpenAPI docs.
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='api:schema'), name='redoc'),

    path('register/', views.register, name='register'),
    path('login/', VerifiedTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', VerifiedTokenRefreshView.as_view(), name='token_refresh'),
    path('classify/', views.classify, name='classify'),
    path('controls/', views.controls, name='controls'),                      # deprecated (legacy CompanyControl)
    path('controls/<int:control_id>/', views.control_detail, name='control_detail'),
    # Phase 3G — modern read endpoints (new architecture).
    path('assessments/', views.assessments, name='assessments'),
    path('evidence-submissions/', views.evidence_submissions, name='evidence_submissions'),
    path('evidence/upload/', views.evidence_upload, name='evidence_upload'),
    path('evidence/<int:evidence_id>/analyze/', views.evidence_analyze, name='evidence_analyze'),
    path('gap-analysis/', views.gap_analysis, name='gap_analysis'),
    path('dashboard/executive/', views.dashboard_executive, name='dashboard_executive'),
    path('dashboard/compliance/', views.dashboard_compliance, name='dashboard_compliance'),
    path('monitoring/scores/', views.monitoring_scores, name='monitoring_scores'),
    path('monitoring/alerts/', views.monitoring_alerts, name='monitoring_alerts'),
    path('auditor/assignments/', views.auditor_assignments, name='auditor_assignments'),
]
