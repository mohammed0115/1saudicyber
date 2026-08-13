from django.urls import path

from . import views

app_name = 'policy_engine'

urlpatterns = [
    path('policy-packs/', views.policy_packs, name='policy-packs'),
    path('policy-versions/<int:policy_version_id>/', views.policy_version_detail, name='policy-version-detail'),
    path('policy-evaluations/', views.evaluate_current_company, name='policy-evaluations'),
    path('canonical-controls/<slug:key>/', views.canonical_control_detail, name='canonical-control-detail'),
]
