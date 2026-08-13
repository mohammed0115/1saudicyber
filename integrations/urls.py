from django.urls import path

from . import views

app_name = 'integrations'

urlpatterns = [
    path('providers/', views.provider_catalog, name='providers'),
    path('connections/', views.connections, name='connections'),
    path('connections/<int:connection_id>/test/', views.connection_test, name='connection-test'),
    path('control-tests/', views.control_test_definitions, name='control-tests'),
    path('control-tests/<int:definition_id>/runs/', views.run_control_test, name='control-test-runs'),
    path('control-test-runs/<int:run_id>/', views.control_test_run_detail, name='control-test-run-detail'),
]
