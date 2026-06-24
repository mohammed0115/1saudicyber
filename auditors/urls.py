from django.urls import path

from . import views

app_name = 'auditors'

urlpatterns = [
    # Company-facing list (root of /auditors/)
    path('', views.auditors_list, name='list'),

    # Auditor onboarding / dashboard (literal prefixes before the <int> assign route)
    path('register/', views.register, name='register'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('assignments/<int:assignment_id>/', views.assignment_detail, name='assignment_detail'),
    path('assignments/<int:assignment_id>/respond/', views.assignment_respond, name='assignment_respond'),

    # Company assigns to a specific auditor
    path('<int:auditor_id>/assign/', views.assign, name='assign'),
]
