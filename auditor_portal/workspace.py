"""Read-only, state-aware auditor review-workspace model.

Computes the review stepper + summary counts from EXISTING data only (company
controls, evidence, auditor notes, document requests, the internal AuditReport).
Never writes, never issues a compliance decision. The verdict/report it reflects
is an INTERNAL human review — never an official certification/accreditation.
"""

# (key, Arabic title) for the 9-step internal review workspace journey.
_STEP_DEFS = [
    ('open_company', 'فتح ملف الشركة'),
    ('scope_review', 'مراجعة نطاق الأطر'),
    ('controls_review', 'مراجعة الضوابط'),
    ('evidence_review', 'مراجعة الأدلة'),
    ('advisory_review', 'مراجعة التحليل الاستشاري'),
    ('auditor_notes', 'إضافة ملاحظات المدقق'),
    ('doc_requests', 'طلب استكمالات من الشركة'),
    ('internal_verdict', 'الحكم الداخلي'),
    ('internal_report', 'التقرير الداخلي'),
]


def review_workspace_summary(assessment):
    """Return {steps, counts...} for the auditor review workspace. Read-only."""
    from compliance.models import CompanyControl, Evidence
    from .models import AuditorNote, DocumentRequest, AuditReport

    company = assessment.company
    ccs = CompanyControl.objects.filter(company=company)
    controls_count = ccs.count()
    evidence_qs = Evidence.objects.filter(company_control__company=company)
    evidence_count = evidence_qs.count()
    # "needs review" = uploaded/extracting/analysing, not yet a settled evidence state.
    needs_review = evidence_qs.filter(
        status__in=('uploaded', 'processing', 'ai_analyzing')).count()

    try:
        from compliance.models import CompanyFrameworkScope
        approved_frameworks = list(
            CompanyFrameworkScope.objects.filter(company=company, status='approved')
            .select_related('framework_version')
            .values_list('framework_version__code', flat=True))
    except Exception:
        approved_frameworks = []

    has_ai = ccs.exclude(ai_verdict='').exists() or evidence_qs.exclude(ai_verdict='').exists()
    notes_count = AuditorNote.objects.filter(assessment=assessment).count()
    docreq_count = DocumentRequest.objects.filter(assessment=assessment).count()
    has_report = (AuditReport.objects.filter(assessment=assessment).exists()
                  or assessment.status == 'completed')

    done_map = {
        'open_company': True,
        'scope_review': bool(approved_frameworks),
        'controls_review': controls_count > 0,
        'evidence_review': evidence_count > 0,
        'advisory_review': has_ai,
        'auditor_notes': notes_count > 0,
        'doc_requests': docreq_count > 0,
        'internal_verdict': has_report,
        'internal_report': assessment.status == 'completed',
    }
    # Steps that legitimately wait on company/data rather than the auditor — shown as
    # 'بانتظار' (not 'محجوب') when not yet satisfied and not the current step.
    data_dependent = {'scope_review', 'controls_review', 'evidence_review', 'advisory_review'}

    steps = []
    current_set = False
    for key, title in _STEP_DEFS:
        done = done_map[key]
        if done:
            status = 'completed'
        elif not current_set:
            status = 'current'
            current_set = True
        elif key in data_dependent:
            status = 'waiting'
        else:
            status = 'waiting'
        steps.append({'key': key, 'title': title, 'status': status})

    return {
        'steps': steps,
        'approved_frameworks': approved_frameworks,
        'controls_count': controls_count,
        'evidence_count': evidence_count,
        'needs_review_count': needs_review,
        'notes_count': notes_count,
        'docreq_count': docreq_count,
        'has_report': has_report,
    }
