from django.urls import path
from . import views

app_name = 'compliance'

urlpatterns = [
    path('controls/', views.controls_list, name='controls_list'),
    path('controls/<int:control_id>/', views.control_detail, name='control_detail'),
    path('controls/<int:control_id>/upload/', views.upload_evidence, name='upload_evidence'),
]
