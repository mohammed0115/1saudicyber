"""
Phase 3H — read-only compliance reporting + gap analysis.

Deterministic, tenant-scoped, READ-ONLY. Builds reports from approved framework
scopes, official controls (framework_version set, is_legacy_import=False),
ControlApplicabilityResult (applicable), ControlAssessment statuses, evidence
checklist/submissions, and AI advisory summaries. It NEVER writes, never creates
CompanyControl, never uses the legacy 334 as an official source, and never treats
AI as a final decision. Unreviewed controls are NEVER counted as compliant.

Standalone module (not a `services/` package) to avoid colliding with compliance/services.py.
"""
from compliance.models import (
    Control, CompanyFrameworkScope, ControlApplicabilityResult, ControlAssessment,
    EvidenceSubmission, EvidenceAnalysisResult,
)

STATUS_KEYS = ['compliant', 'partially_compliant', 'non_compliant',
               'not_applicable', 'needs_more_evidence', 'not_reviewed']
GAP_STATUSES = ['non_compliant', 'partially_compliant', 'needs_more_evidence', 'not_reviewed']


def get_approved_framework_versions(company):
    """FrameworkVersions approved for the company (scope.status='approved')."""
    return [s.framework_version for s in CompanyFrameworkScope.objects
            .filter(company=company, status='approved')
            .select_related('framework_version', 'framework_version__framework')]


def _applicable_official_controls(company, framework_version=None):
    """Applicable OFFICIAL controls for the company (optionally one framework version)."""
    cars = (ControlApplicabilityResult.objects
            .filter(company=company, decision='applicable',
                    control__framework_version__isnull=False, control__is_legacy_import=False)
            .select_related('control', 'control__framework_version'))
    if framework_version is not None:
        cars = cars.filter(control__framework_version=framework_version)
    return cars


def _assessment_map(company):
    return {a.control_id: a for a in ControlAssessment.objects.filter(company=company)}


def calculate_assessment_counts(controls, amap):
    """Count assessment statuses over a control iterable; unassessed -> not_reviewed."""
    counts = {k: 0 for k in STATUS_KEYS}
    for c in controls:
        a = amap.get(c.id)
        status = a.status if a else 'not_reviewed'
        counts[status] = counts.get(status, 0) + 1
    return counts


def _coverage(company, control_ids):
    """Number of controls (within control_ids) with >=1 evidence submission."""
    covered = set(EvidenceSubmission.objects
                  .filter(company=company,
                          checklist_item__evidence_requirement__control_id__in=control_ids)
                  .values_list('checklist_item__evidence_requirement__control_id', flat=True))
    return len(covered)


def build_executive_summary(company):
    """High-level counts across all applicable official controls. Read-only."""
    cars = list(_applicable_official_controls(company))
    controls = [car.control for car in cars]
    control_ids = [c.id for c in controls]
    amap = _assessment_map(company)
    counts = calculate_assessment_counts(controls, amap)
    total = len(controls)
    assessed = total - counts['not_reviewed']
    coverage = _coverage(company, control_ids)
    return {
        'company': company,
        'frameworks': get_approved_framework_versions(company),
        'total_applicable': total,
        'counts': counts,
        'assessed': assessed,
        'gaps': sum(counts[s] for s in GAP_STATUSES),
        'completion_percentage': round(assessed / total * 100, 1) if total else 0.0,
        'compliance_percentage': round(counts['compliant'] / total * 100, 1) if total else 0.0,
        'evidence_submission_count': EvidenceSubmission.objects.filter(company=company).count(),
        'evidence_coverage_count': coverage,
        'evidence_coverage_percentage': round(coverage / total * 100, 1) if total else 0.0,
    }


def build_framework_gap_analysis(company, framework_version=None):
    """Per-framework gap breakdown. Read-only."""
    fvs = ([framework_version] if framework_version is not None
           else get_approved_framework_versions(company))
    amap = _assessment_map(company)
    out = []
    for fv in fvs:
        cars = list(_applicable_official_controls(company, framework_version=fv))
        controls = [car.control for car in cars]
        counts = calculate_assessment_counts(controls, amap)
        gaps = []
        remediation_required = 0
        for c in controls:
            a = amap.get(c.id)
            status = a.status if a else 'not_reviewed'
            if status in GAP_STATUSES:
                gaps.append({'control_id': c.control_id, 'title': c.title, 'status': status,
                             'remediation_due': a.remediation_due_date if a else None,
                             'auditor_notes': a.auditor_notes if a else ''})
            if a and a.remediation_required:
                remediation_required += 1
        out.append({
            'framework_version': fv,
            'source_document': fv.source_document,
            'total_applicable': len(controls),
            'counts': counts,
            'gaps': gaps,
            'remediation_required_count': remediation_required,
        })
    return out


def build_evidence_matrix(company, framework_version=None):
    """Row per applicable official control with evidence/AI/assessment state. Read-only."""
    cars = list(_applicable_official_controls(company, framework_version=framework_version))
    amap = _assessment_map(company)
    # Pre-aggregate submissions/analyses per control.
    sub_counts, latest_sub = {}, {}
    for s in (EvidenceSubmission.objects.filter(company=company)
              .select_related('checklist_item__evidence_requirement')):
        cid = s.checklist_item.evidence_requirement.control_id
        sub_counts[cid] = sub_counts.get(cid, 0) + 1
        latest_sub.setdefault(cid, s.get_status_display())  # qs ordered -uploaded_at
    latest_ai = {}
    for an in EvidenceAnalysisResult.objects.filter(company=company):
        latest_ai.setdefault(an.control_id, an.get_status_display())

    rows = []
    for car in cars:
        c = car.control
        a = amap.get(c.id)
        rows.append({
            'framework': c.framework_version.code,
            'control_id': c.control_id,
            'title': c.title,
            'requirement_count': c.evidence_requirements.count(),
            'submission_count': sub_counts.get(c.id, 0),
            'latest_submission_status': latest_sub.get(c.id, '—'),
            'latest_ai_status': latest_ai.get(c.id, '—'),
            'assessment_status': a.get_status_display() if a else 'Not Reviewed',
            'assessment_status_key': a.status if a else 'not_reviewed',
            'reviewed_by': str(a.reviewed_by) if a and a.reviewed_by else '',
            'reviewed_at': a.reviewed_at if a else None,
        })
    return rows
