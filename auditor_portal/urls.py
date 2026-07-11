from django.urls import path
from . import views

app_name = 'auditor_portal'

urlpatterns = [
    path('', views.auditor_dashboard, name='dashboard'),
    path('assessment/<int:assessment_id>/', views.review_assessment, name='review_assessment'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/', views.review_control, name='review_control'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/note/', views.add_note, name='add_note'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/request-doc/', views.request_document, name='request_document'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/verdict/', views.save_verdict, name='save_verdict'),
    path('assessment/<int:assessment_id>/submit-report/', views.submit_report, name='submit_report'),

    # RFI lifecycle (auditor)
    path('rfi/<int:rfi_id>/close/', views.close_rfi, name='close_rfi'),
    path('rfi/<int:rfi_id>/cancel/', views.cancel_rfi, name='cancel_rfi'),
    path('rfi/<int:rfi_id>/reopen/', views.reopen_rfi, name='reopen_rfi'),

    # Company-side RFI (company users)
    path('company/rfi/', views.company_rfi_list, name='company_rfi_list'),
    path('company/rfi/<int:rfi_id>/respond/', views.company_rfi_respond, name='company_rfi_respond'),
]
