from django.urls import path
from . import views

app_name = 'ai_engine'

urlpatterns = [
    path('classify/', views.run_classification, name='classify'),
    path('gap-analysis/', views.run_gap_analysis, name='gap_analysis'),
    path('classification-result/', views.classification_result, name='classification_result'),
]
