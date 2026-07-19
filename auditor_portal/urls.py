from django.urls import path
from . import views

app_name = 'auditor_portal'

urlpatterns = [
    path('', views.auditor_dashboard, name='dashboard'),
    path('queue/', views.review_queue, name='review_queue'),
    path('assessment/<int:assessment_id>/', views.review_assessment, name='review_assessment'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/', views.review_control, name='review_control'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/note/', views.add_note, name='add_note'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/request-doc/', views.request_document, name='request_document'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/verdict/', views.save_verdict, name='save_verdict'),
    path('assessment/<int:assessment_id>/control/<int:control_id>/finding/', views.add_finding, name='add_finding'),

    # G2 — findings lifecycle + corrective actions (CAPA)
    path('finding/<int:finding_id>/capa/', views.add_corrective_action, name='add_corrective_action'),
    path('finding/<int:finding_id>/status/', views.update_finding_status, name='update_finding_status'),
    path('capa/<int:action_id>/verify/', views.verify_corrective_action, name='verify_corrective_action'),
    # Company-side findings + remediation
    path('company/findings/', views.company_findings, name='company_findings'),
    path('company/findings/<int:finding_id>/capa/', views.company_add_corrective_action, name='company_add_corrective_action'),
    path('company/capa/<int:action_id>/status/', views.company_update_capa, name='company_update_capa'),

    # G5 — per-company internal message thread (company + assigned auditor + staff)
    path('company/<int:company_id>/thread/', views.message_thread, name='message_thread'),
    path('company/<int:company_id>/thread/post/', views.post_message, name='post_message'),
    path('assessment/<int:assessment_id>/submit-report/', views.submit_report, name='submit_report'),

    # RFI lifecycle (auditor)
    path('rfi/<int:rfi_id>/close/', views.close_rfi, name='close_rfi'),
    path('rfi/<int:rfi_id>/cancel/', views.cancel_rfi, name='cancel_rfi'),
    path('rfi/<int:rfi_id>/reopen/', views.reopen_rfi, name='reopen_rfi'),

    # Company-side RFI (company users)
    path('company/rfi/', views.company_rfi_list, name='company_rfi_list'),
    path('company/rfi/<int:rfi_id>/respond/', views.company_rfi_respond, name='company_rfi_respond'),
]
