"""Phase 8I-SUBSCRIPTION-A — company billing routes."""
from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_home, name='home'),
    path('start-trial/', views.start_trial, name='start_trial'),
    path('select-plan/', views.select_plan, name='select_plan'),
]
