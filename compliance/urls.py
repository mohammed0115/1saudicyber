from django.urls import path
from . import views

app_name = 'compliance'

urlpatterns = [
    # Phase 3I — read-only journey dashboard / overview
    path('dashboard/', views.journey_dashboard, name='dashboard'),

    path('controls/', views.controls_list, name='controls_list'),
    path('controls/<int:control_id>/', views.control_detail, name='control_detail'),
    path('controls/<int:control_id>/upload/', views.upload_evidence, name='upload_evidence'),

    # Phase 3B — Company Intake Wizard + Framework Applicability review
    path('intake/', views.intake_wizard, name='intake'),
    # Phase 6A — advisory Smart Classification summary (read-only)
    path('classification/', views.classification_summary, name='classification'),
    # Phase 6B — advisory control-applicability preview (read-only)
    path('applicability/', views.applicability_preview, name='applicability_preview'),
    path('intake/review/', views.applicability_review, name='applicability_review'),

    # Phase 3C — Framework approval (scope) + control applicability plan
    path('frameworks/scope/<int:scope_id>/approve/', views.approve_framework_scope_view, name='approve_scope'),
    path('frameworks/scope/<int:scope_id>/reject/', views.reject_framework_scope_view, name='reject_scope'),
    path('frameworks/scope/<int:scope_id>/generate-plan/', views.generate_control_plan_view, name='generate_plan'),
    path('control-plan/', views.control_plan, name='control_plan'),

    # Phase 3D — Evidence checklist planning (no upload here)
    path('evidence-checklist/', views.evidence_checklist, name='evidence_checklist'),
    path('evidence-checklist/generate/', views.generate_evidence_checklist_view, name='generate_evidence_checklist'),

    # Phase 3E — Evidence Upload v2 (linked to checklist items)
    path('evidence-checklist/<int:item_id>/upload/', views.evidence_upload_v2, name='evidence_upload_v2'),
    path('evidence-checklist/<int:item_id>/submissions/', views.evidence_submission_list, name='evidence_submission_list'),
    path('evidence-submissions/<int:submission_id>/', views.evidence_submission_detail, name='evidence_submission_detail'),
    # Phase 6C — read-only text-extraction preview
    path('evidence-submissions/<int:submission_id>/extraction/', views.evidence_extraction_preview, name='evidence_extraction'),
    # Phase 6C-FIX-A — run + persist a text-extraction attempt (POST, owner-only)
    path('evidence-submissions/<int:submission_id>/extract-text/', views.run_evidence_extraction, name='run_evidence_extraction'),
    # Phase 6D — advisory AI evidence analysis (preview + POST run, owner-only)
    path('evidence-submissions/<int:submission_id>/ai-analysis/', views.evidence_ai_analysis_preview, name='evidence_ai_analysis'),
    path('evidence-submissions/<int:submission_id>/run-ai-analysis/', views.run_evidence_ai_analysis, name='run_evidence_ai_analysis'),
    # Phase 6E — rule engine suggested status (preview + POST run, owner-only)
    path('evidence-submissions/<int:submission_id>/rule-evaluation/', views.evidence_rule_evaluation_preview, name='evidence_rule_evaluation'),
    path('evidence-submissions/<int:submission_id>/run-rule-evaluation/', views.run_evidence_rule_evaluation, name='run_evidence_rule_evaluation'),
    # Phase 6F — auditor final verdict (GET review + POST verdict; staff/assigned auditor)
    path('evidence-submissions/<int:submission_id>/auditor-verdict/', views.auditor_verdict_view, name='auditor_verdict'),

    # Phase 3F — advisory analysis trigger (staff-only)
    path('evidence-submissions/<int:submission_id>/analyze/', views.analyze_submission_view, name='analyze_submission'),

    # Phase 3G — Auditor review + control assessment
    path('auditor-review/', views.auditor_review_queue, name='auditor_review_queue'),
    path('auditor-review/generate/', views.generate_assessments_view, name='generate_assessments'),
    path('auditor-review/<int:assessment_id>/', views.auditor_review_detail, name='auditor_review_detail'),

    # Phase 3H — read-only compliance reports + gap analysis + exports
    path('reports/', views.reports_index, name='reports_index'),
    # Phase 7B — internal auditor-reviewed report (subscription-gated)
    path('reports/auditor-reviewed/', views.auditor_reviewed_report, name='auditor_reviewed_report'),
    path('reports/executive-summary/', views.report_executive_summary, name='report_executive_summary'),
    path('reports/gap-analysis/', views.report_gap_analysis, name='report_gap_analysis'),
    path('reports/evidence-matrix/', views.report_evidence_matrix, name='report_evidence_matrix'),
    path('reports/evidence-matrix.csv', views.export_evidence_matrix_csv, name='export_evidence_matrix_csv'),
    path('reports/evidence-matrix.xlsx', views.export_evidence_matrix_xlsx, name='export_evidence_matrix_xlsx'),
    path('reports/framework/<int:framework_version_id>/', views.report_framework, name='report_framework'),
]
