from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [
    path('', views.compliance_hub, name='hub'),
    path('realtime/', views.realtime_monitoring, name='realtime'),
    path('api/scores/', views.score_api, name='score_api'),
    path('api/stream/', views.event_stream, name='event_stream'),

    # Phase 5B — Continuous Monitoring Foundation
    path('continuous/', views.monitoring_overview, name='overview'),
    path('checks/', views.checks_list, name='checks'),
    path('findings/', views.findings_list, name='findings'),
    path('assignment/<int:assignment_id>/', views.auditor_monitoring_view, name='auditor_view'),
]
