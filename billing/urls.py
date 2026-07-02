"""Phase 8I-SUBSCRIPTION-A — company billing routes."""
from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_home, name='home'),
    path('start-trial/', views.start_trial, name='start_trial'),
    path('select-plan/', views.select_plan, name='select_plan'),
    path('payments/<int:payment_id>/checkout/', views.checkout, name='checkout'),
    path('moyasar/callback/', views.moyasar_callback, name='moyasar_callback'),
    path('moyasar/webhook/', views.moyasar_webhook, name='moyasar_webhook'),
]
