from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [
    path('', views.compliance_hub, name='hub'),
    path('realtime/', views.realtime_monitoring, name='realtime'),
    path('api/scores/', views.score_api, name='score_api'),
    path('api/stream/', views.event_stream, name='event_stream'),
]
