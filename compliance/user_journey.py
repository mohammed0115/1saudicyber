"""
Phase 3I — read-only user-journey status for the CyberTrust dashboard.

Deterministic, tenant-scoped, READ-ONLY. Computes where a company stands in the
end-to-end workflow (intake -> framework approval -> control plan -> evidence
checklist -> evidence upload -> advisory analysis -> auditor review -> reports)
and the single next recommended action.

It NEVER writes, never creates CompanyControl, never uses the legacy 334 as an
official source, and never lets AI decide compliance. Official controls only:
framework_version set AND is_legacy_import=False. Unreviewed assessments are
never treated as completed/compliant.
"""
from compliance.models import (
    CompanyIntakeProfile, FrameworkApplicabilityResult, CompanyFrameworkScope,
    ControlApplicabilityResult, EvidenceChecklistItem, EvidenceSubmission,
    EvidenceAnalysisResult, ControlAssessment,
)

# Journey stage status values (UX-only; no compliance meaning).
NOT_STARTED = 'not_started'
IN_PROGRESS = 'in_progress'
COMPLETED = 'completed'
NEEDS_ATTENTION = 'needs_attention'

# Ordered stage keys/titles. Order drives progress and the next-action ladder.
STAGE_ORDER = [
    'intake', 'framework_applicability', 'framework_approval', 'control_plan',
    'evidence_checklist', 'evidence_upload', 'ai_analysis', 'auditor_review', 'reports',
]


def _applicable_official_controls_qs(company):
    """Applicable OFFICIAL controls planned for the company (read-only queryset)."""
    return (ControlApplicabilityResult.objects
            .filter(company=company, decision='applicable',
                    control__framework_version__isnull=False, control__is_legacy_import=False))


def _gather_metrics(company):
    """Single read-only pass of the counts every stage needs."""
    intake = CompanyIntakeProfile.objects.filter(company=company).first()
    applicable_frameworks = FrameworkApplicabilityResult.objects.filter(
        company=company, decision='applicable').count()
    framework_results = FrameworkApplicabilityResult.objects.filter(company=company).count()
    proposed_scopes = CompanyFrameworkScope.objects.filter(company=company, status='proposed').count()
    approved_scopes = CompanyFrameworkScope.objects.filter(company=company, status='approved').count()
    applicable_controls = _applicable_official_controls_qs(company).count()
    checklist_items = EvidenceChecklistItem.objects.filter(company=company).count()
    submissions = EvidenceSubmission.objects.filter(company=company).count()
    analyses = EvidenceAnalysisResult.objects.filter(company=company).count()
    assessments_total = ControlAssessment.objects.filter(company=company).count()
    assessments_not_reviewed = ControlAssessment.objects.filter(
        company=company, status='not_reviewed').count()
    assessments_reviewed = assessments_total - assessments_not_reviewed
    return {
        'intake': intake,
        'framework_results': framework_results,
        'applicable_frameworks': applicable_frameworks,
        'proposed_scopes': proposed_scopes,
        'approved_scopes': approved_scopes,
        'applicable_controls': applicable_controls,
        'checklist_items': checklist_items,
        'submissions': submissions,
        'analyses': analyses,
        'pending_analysis': max(0, submissions - analyses),
        'assessments_total': assessments_total,
        'assessments_not_reviewed': assessments_not_reviewed,
        'assessments_reviewed': assessments_reviewed,
    }


def build_company_journey_status(company):
    """Return an ordered list of journey-stage dicts for the company. Read-only.

    Each stage dict: key, order, title, status, explanation, metric (str),
    action_url_name, action_label.
    """
    m = _gather_metrics(company)
    intake = m['intake']

    # 1) Intake profile
    if intake is None:
        intake_status, intake_metric = NOT_STARTED, 'لا يوجد ملف تصنيف'
    elif intake.review_status in ('completed', 'reviewed'):
        intake_status, intake_metric = COMPLETED, intake.get_review_status_display()
    else:
        intake_status, intake_metric = IN_PROGRESS, intake.get_review_status_display()

    # 2) Framework applicability
    if m['framework_results']:
        fa_status = COMPLETED
    elif intake is not None:
        fa_status = IN_PROGRESS
    else:
        fa_status = NOT_STARTED

    # 3) Framework approval (scope)
    if m['approved_scopes']:
        approval_status = COMPLETED
    elif m['proposed_scopes']:
        approval_status = NEEDS_ATTENTION
    else:
        approval_status = NOT_STARTED

    # 4) Control plan
    if m['applicable_controls']:
        plan_status = COMPLETED
    elif m['approved_scopes']:
        plan_status = IN_PROGRESS
    else:
        plan_status = NOT_STARTED

    # 5) Evidence checklist
    if m['checklist_items']:
        checklist_status = COMPLETED
    elif m['applicable_controls']:
        checklist_status = IN_PROGRESS
    else:
        checklist_status = NOT_STARTED

    # 6) Evidence upload
    if m['submissions']:
        upload_status = COMPLETED
    elif m['checklist_items']:
        upload_status = IN_PROGRESS
    else:
        upload_status = NOT_STARTED

    # 7) AI advisory analysis (advisory only — never a compliance decision)
    if m['submissions'] == 0:
        ai_status = NOT_STARTED
    elif m['pending_analysis'] == 0 and m['analyses'] > 0:
        ai_status = COMPLETED
    else:
        ai_status = IN_PROGRESS

    # 8) Auditor review (the auditor's final decision)
    if m['assessments_total'] == 0:
        review_status = NOT_STARTED
    elif m['assessments_not_reviewed'] == 0:
        review_status = COMPLETED
    elif m['assessments_reviewed'] > 0:
        review_status = IN_PROGRESS
    else:
        review_status = NEEDS_ATTENTION

    # 9) Reports (meaningful once at least one assessment is reviewed)
    reports_status = COMPLETED if m['assessments_reviewed'] > 0 else NOT_STARTED

    stages = [
        {
            'key': 'intake', 'title': 'الملف والتصنيف (Intake Profile)',
            'status': intake_status,
            'explanation': 'استكمل ملف تصنيف المنشأة لحساب الأطر المنطبقة.',
            'metric': intake_metric,
            'action_url_name': 'compliance:intake', 'action_label': 'فتح التصنيف',
        },
        {
            'key': 'framework_applicability', 'title': 'انطباق الأطر (Framework Applicability)',
            'status': fa_status,
            'explanation': 'الأطر المقترحة بناءً على التصنيف.',
            'metric': f"{m['applicable_frameworks']} إطار منطبق",
            'action_url_name': 'compliance:applicability_review', 'action_label': 'مراجعة الأطر',
        },
        {
            'key': 'framework_approval', 'title': 'اعتماد الأطر (Framework Approval)',
            'status': approval_status,
            'explanation': 'اعتماد نطاق الأطر المنطبقة (صلاحية موظّف/مدقّق).',
            'metric': f"{m['approved_scopes']} معتمد / {m['proposed_scopes']} مقترح",
            'action_url_name': 'compliance:applicability_review', 'action_label': 'اعتماد الأطر',
        },
        {
            'key': 'control_plan', 'title': 'خطة الضوابط (Control Plan)',
            'status': plan_status,
            'explanation': 'الضوابط الرسمية المنطبقة تحت الأطر المعتمدة.',
            'metric': f"{m['applicable_controls']} ضابط منطبق",
            'action_url_name': 'compliance:control_plan', 'action_label': 'خطة الضوابط',
        },
        {
            'key': 'evidence_checklist', 'title': 'قائمة الأدلة (Evidence Checklist)',
            'status': checklist_status,
            'explanation': 'مهام أدلة مخطّطة للضوابط المنطبقة.',
            'metric': f"{m['checklist_items']} عنصر",
            'action_url_name': 'compliance:evidence_checklist', 'action_label': 'قائمة الأدلة',
        },
        {
            'key': 'evidence_upload', 'title': 'رفع الأدلة (Evidence Upload)',
            'status': upload_status,
            'explanation': 'رفع الأدلة المرتبطة بعناصر القائمة.',
            'metric': f"{m['submissions']} ملف",
            'action_url_name': 'compliance:evidence_checklist', 'action_label': 'رفع الأدلة',
        },
        {
            'key': 'ai_analysis', 'title': 'التحليل الاستشاري (AI Advisory)',
            'status': ai_status,
            'explanation': 'تحليل استشاري فقط — لا يتّخذ قرار الامتثال.',
            'metric': f"{m['analyses']} مُحلَّل / {m['pending_analysis']} قيد الانتظار",
            'action_url_name': 'compliance:evidence_checklist', 'action_label': 'إدارة الأدلة',
        },
        {
            'key': 'auditor_review', 'title': 'مراجعة المدقّق (Auditor Review)',
            'status': review_status,
            'explanation': 'القرار النهائي للامتثال يتّخذه المدقّق.',
            'metric': f"{m['assessments_reviewed']} مُراجَع / {m['assessments_total']} إجمالي",
            'action_url_name': 'compliance:auditor_review_queue', 'action_label': 'قائمة المراجعة',
        },
        {
            'key': 'reports', 'title': 'التقارير (Reports)',
            'status': reports_status,
            'explanation': 'تقارير للقراءة فقط تصبح ذات معنى بعد قرارات المدقّق.',
            'metric': 'متاحة' if reports_status == COMPLETED else 'بانتظار التقييم',
            'action_url_name': 'compliance:reports_index', 'action_label': 'عرض التقارير',
        },
    ]
    for i, s in enumerate(stages):
        s['order'] = i + 1
    return stages


def get_next_recommended_action(company):
    """Deterministic next-step for the company. Read-only.

    Returns a dict: stage_key, message, action_url_name, action_label.
    Mirrors the journey ladder; gates on existence, never on AI output.
    """
    m = _gather_metrics(company)

    def action(key, url_name, label, message):
        return {'stage_key': key, 'action_url_name': url_name,
                'action_label': label, 'message': message}

    if m['intake'] is None:
        return action('intake', 'compliance:intake', 'فتح التصنيف',
                      'Complete intake profile')
    if not m['approved_scopes']:
        return action('framework_approval', 'compliance:applicability_review', 'مراجعة الأطر',
                      'Review and approve applicable frameworks')
    if not m['applicable_controls']:
        return action('control_plan', 'compliance:control_plan', 'خطة الضوابط',
                      'Generate control plan')
    if not m['checklist_items']:
        return action('evidence_checklist', 'compliance:evidence_checklist', 'قائمة الأدلة',
                      'Generate evidence checklist')
    if not m['submissions']:
        return action('evidence_upload', 'compliance:evidence_checklist', 'رفع الأدلة',
                      'Upload evidence')
    if not m['analyses']:
        return action('ai_analysis', 'compliance:evidence_checklist', 'إدارة الأدلة',
                      'Run advisory analysis')
    if not m['assessments_total']:
        return action('auditor_review', 'compliance:auditor_review_queue', 'بدء المراجعة',
                      'Start auditor review')
    return action('reports', 'compliance:reports_index', 'عرض التقارير', 'View reports')


def calculate_journey_progress(company):
    """Return {'completed', 'total', 'percentage'} of completed journey stages. Read-only."""
    stages = build_company_journey_status(company)
    total = len(stages)
    completed = sum(1 for s in stages if s['status'] == COMPLETED)
    return {
        'completed': completed,
        'total': total,
        'percentage': round(completed / total * 100, 1) if total else 0.0,
    }
