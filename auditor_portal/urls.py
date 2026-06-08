from django.urls import path
from . import views

app_name = 'auditor_portal'

urlpatterns = [
    path('', views.auditor_dashboard, name='dashboard'),
    path('assessment/<int:assessment_id>/', views.review_assessment, name='review_assessment'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/', views.review_control, name='review_control'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/note/', views.add_note, name='add_note'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/request-doc/', views.request_document, name='request_document'),
    path('assessment/<int:assessment_id>/submit-report/', views.submit_report, name='submit_report'),
]
