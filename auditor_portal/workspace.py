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
    from .models import AuditorNote, DocumentRequest, AuditReport, AuditorControlVerdict

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

    # Internal verdict coverage (per control).
    verdicts = AuditorControlVerdict.objects.filter(assessment=assessment)
    vcounts = {'compliant': 0, 'partially_compliant': 0, 'non_compliant': 0,
               'needs_more_evidence': 0, 'not_applicable': 0}
    reviewed_controls = 0
    for v in verdicts:
        if v.status in vcounts:
            vcounts[v.status] += 1
        if v.status in AuditorControlVerdict.REVIEWED_STATES:
            reviewed_controls += 1
    unreviewed_controls = max(0, controls_count - reviewed_controls)

    # RFI lifecycle.
    reqs = DocumentRequest.objects.filter(assessment=assessment)
    docreq_count = reqs.count()
    open_rfi = reqs.filter(status__in=DocumentRequest.OPEN_STATES).count()
    responded_rfi = reqs.filter(status='responded').count()

    has_report = (AuditReport.objects.filter(assessment=assessment).exists()
                  or assessment.status == 'completed')
    # Report readiness: hard-blocked while any RFI is open; ready once at least one
    # verdict exists and no RFI is open. Internal review only — never a certificate.
    report_blocked = open_rfi > 0
    report_ready = (reviewed_controls > 0) and (open_rfi == 0)
    full_coverage = (controls_count > 0) and (unreviewed_controls == 0)

    done_map = {
        'open_company': True,
        'scope_review': bool(approved_frameworks),
        'controls_review': controls_count > 0,
        'evidence_review': evidence_count > 0,
        'advisory_review': has_ai,
        'auditor_notes': notes_count > 0,
        'doc_requests': docreq_count > 0,
        'internal_verdict': reviewed_controls > 0,
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
        # verdict coverage
        'reviewed_controls': reviewed_controls,
        'unreviewed_controls': unreviewed_controls,
        'verdict_counts': vcounts,
        # RFI + readiness
        'open_rfi': open_rfi,
        'responded_rfi': responded_rfi,
        'report_blocked': report_blocked,
        'report_ready': report_ready,
        'full_coverage': full_coverage,
    }
