from django.urls import path
from . import views

app_name = 'compliance'

urlpatterns = [
    path('controls/', views.controls_list, name='controls_list'),
    path('controls/<int:control_id>/', views.control_detail, name='control_detail'),
    path('controls/<int:control_id>/upload/', views.upload_evidence, name='upload_evidence'),

    # Phase 3B — Company Intake Wizard + Framework Applicability review
    path('intake/', views.intake_wizard, name='intake'),
    path('intake/review/', views.applicability_review, name='applicability_review'),

    # Phase 3C — Framework approval (scope) + control applicability plan
    path('frameworks/scope/<int:scope_id>/approve/', views.approve_framework_scope_view, name='approve_scope'),
    path('frameworks/scope/<int:scope_id>/reject/', views.reject_framework_scope_view, name='reject_scope'),
    path('frameworks/scope/<int:scope_id>/generate-plan/', views.generate_control_plan_view, name='generate_plan'),
    path('control-plan/', views.control_plan, name='control_plan'),

    # Phase 3D — Evidence checklist planning (no upload here)
    path('evidence-checklist/', views.evidence_checklist, name='evidence_checklist'),
    path('evidence-checklist/generate/', views.generate_evidence_checklist_view, name='generate_evidence_checklist'),
]
