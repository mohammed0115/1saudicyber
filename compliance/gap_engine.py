"""Phase 8F-GAP-ENGINE-A — deterministic, evidence-aware gap analysis engine.

Computes a PRELIMINARY, INTERNAL readiness status for each applicable official
control of a company, from existing data only:

    scope not applicable                              -> not_applicable
    auditor ControlAssessment == compliant            -> compliant
    auditor ControlAssessment == not_applicable       -> not_applicable
    no evidence uploaded                              -> missing
    evidence uploaded, readable text extracted        -> partially_compliant
    evidence uploaded, no readable text extracted     -> needs_review
    otherwise / insufficient data                     -> needs_review

Guarantees:
* Deterministic. No AI, no network, no randomness.
* Never issues an official certification/accreditation or a final compliance
  decision — this is evidence-based preliminary readiness that requires human review.
* Read-only w.r.t. compliance calculations and control counts; the only writes are
  the company's own ControlGapAssessment rows (upsert) + an audit entry.
"""
from django.utils import timezone

# Readiness weights for the per-framework score (compliant=100, partial=50, else 0).
_WEIGHT = {'compliant': 100, 'partially_compliant': 50, 'missing': 0,
           'needs_review': 0, 'not_applicable': 0}
STATUS_KEYS = ['compliant', 'partially_compliant', 'missing', 'needs_review', 'not_applicable']

STATUS_AR = {
    'compliant': 'جاهز (أولي)',
    'partially_compliant': 'جاهزية جزئية',
    'missing': 'دليل مفقود',
    'needs_review': 'يتطلب مراجعة',
    'not_applicable': 'غير منطبق',
}


def _evidence_stats_for_control(company, control):
    """(evidence_count, extracted_text_available_count) for one control (read-only)."""
    from .models import EvidenceSubmission
    subs = list(EvidenceSubmission.objects.filter(
        company=company,
        checklist_item__evidence_requirement__control=control)
        .select_related('text_extraction'))
    evidence_count = len(subs)
    text_count = 0
    for s in subs:
        ext = getattr(s, 'text_extraction', None)
        if ext is not None and ext.has_text:
            text_count += 1
    return evidence_count, text_count


def compute_control_gap(company, control, applicability_decision, assessment_status=None):
    """Return a dict {status, score, evidence_count, extracted_text_available_count, reason}.

    Pure function of the inputs — deterministic and side-effect free.
    """
    # 1) Not applicable in scope (or auditor marked not applicable).
    if applicability_decision == 'not_applicable' or assessment_status == 'not_applicable':
        return dict(status='not_applicable', score=0, evidence_count=0,
                    extracted_text_available_count=0,
                    reason='الضابط غير منطبق ضمن نطاق المنشأة · Control is out of scope (not applicable).')

    # 2) Auditor/internal assessment already accepts the control.
    if assessment_status == 'compliant':
        ec, tc = _evidence_stats_for_control(company, control)
        return dict(status='compliant', score=100, evidence_count=ec,
                    extracted_text_available_count=tc,
                    reason='مراجعة داخلية من المدقق: مقبول (أولي) · Internal auditor assessment: acceptable.')

    # 3) Evidence-based deterministic rules.
    ec, tc = _evidence_stats_for_control(company, control)
    if ec == 0:
        return dict(status='missing', score=0, evidence_count=0, extracted_text_available_count=0,
                    reason='لم تُرفع أي أدلة لهذا الضابط · No evidence uploaded for this control.')
    if tc > 0:
        return dict(status='partially_compliant', score=50, evidence_count=ec,
                    extracted_text_available_count=tc,
                    reason='تم رفع أدلة مع نص قابل للقراءة — جاهزية جزئية بانتظار مراجعة بشرية · '
                           'Evidence uploaded with readable text; preliminary partial readiness pending human review.')
    return dict(status='needs_review', score=0, evidence_count=ec, extracted_text_available_count=0,
                reason='تم رفع أدلة دون نص قابل للاستخراج — تتطلب مراجعة يدوية · '
                       'Evidence uploaded but no extractable text; requires human review.')


def recalculate_company_gap(company, actor=None):
    """Recompute + upsert ControlGapAssessment for every applicable official control.

    Idempotent. Returns a summary dict. Writes an audit entry (never blocks).
    Handles an empty company gracefully (no controls -> empty summary, no error).
    """
    from .models import ControlApplicabilityResult, ControlGapAssessment
    from .reporting import _assessment_map

    amap = _assessment_map(company)  # control_id -> ControlAssessment
    cars = (ControlApplicabilityResult.objects
            .filter(company=company, control__framework_version__isnull=False,
                    control__is_legacy_import=False)
            .select_related('control', 'control__framework_version'))

    assessed = 0
    for car in cars:
        control = car.control
        a = amap.get(control.id)
        result = compute_control_gap(company, control, car.decision,
                                     assessment_status=a.status if a else None)
        ControlGapAssessment.objects.update_or_create(
            company=company, control=control,
            defaults=dict(
                framework_version=control.framework_version,
                status=result['status'], score=result['score'],
                evidence_count=result['evidence_count'],
                extracted_text_available_count=result['extracted_text_available_count'],
                reason=result['reason'], calculated_by='deterministic_v1',
            ),
        )
        assessed += 1

    summary = get_company_gap_summary(company)
    _audit_gap_run(actor, company, assessed, summary)
    return summary


def _blank_counts():
    return {k: 0 for k in STATUS_KEYS}


def get_company_gap_summary(company):
    """Read-only aggregate over stored ControlGapAssessment rows.

    Returns {frameworks: [...], overall: {...}, calculated_at, total}. Never 500s
    when there are no rows yet.
    """
    from .models import ControlGapAssessment
    rows = list(ControlGapAssessment.objects.filter(company=company)
                .select_related('framework_version', 'control'))
    by_fw = {}
    overall = _blank_counts()
    latest = None
    for r in rows:
        overall[r.status] = overall.get(r.status, 0) + 1
        if latest is None or (r.calculated_at and r.calculated_at > latest):
            latest = r.calculated_at
        key = r.framework_version_id
        fw = by_fw.setdefault(key, {
            'framework_version': r.framework_version,
            'code': r.framework_version.code if r.framework_version else '—',
            'counts': _blank_counts(), 'total': 0})
        fw['counts'][r.status] = fw['counts'].get(r.status, 0) + 1
        fw['total'] += 1

    frameworks = []
    for fw in by_fw.values():
        fw['readiness_percent'] = _readiness_percent(fw['counts'])
        fw['applicable_total'] = fw['total'] - fw['counts'].get('not_applicable', 0)
        frameworks.append(fw)
    frameworks.sort(key=lambda f: f['code'])

    return {
        'frameworks': frameworks,
        'overall': overall,
        'overall_readiness_percent': _readiness_percent(overall),
        'total': len(rows),
        'missing_count': overall.get('missing', 0),
        'needs_review_count': overall.get('needs_review', 0),
        'calculated_at': latest,
    }


def _readiness_percent(counts):
    """Weighted readiness % over APPLICABLE controls (excludes not_applicable)."""
    applicable = sum(counts.get(k, 0) for k in STATUS_KEYS if k != 'not_applicable')
    if applicable <= 0:
        return 0
    earned = sum(counts.get(k, 0) * _WEIGHT[k] for k in STATUS_KEYS)
    return round(earned / applicable)


def _audit_gap_run(actor, company, assessed, summary):
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action='gap_recalculated',
            path='/compliance/gap-analysis/',
            metadata={
                'company_id': getattr(company, 'id', None),
                'controls_assessed': assessed,
                'overall_readiness_percent': summary.get('overall_readiness_percent', 0),
                'counts': summary.get('overall', {}),
                'framework_count': len(summary.get('frameworks', [])),
                'performed_by': getattr(actor, 'email', ''),
            },
        )
    except Exception:
        pass


def gap_rows(company):
    """Per-control gap rows for the dashboard list (read-only, ordered by status severity)."""
    from .models import ControlGapAssessment
    order = {'missing': 0, 'needs_review': 1, 'partially_compliant': 2,
             'compliant': 3, 'not_applicable': 4}
    rows = list(ControlGapAssessment.objects.filter(company=company)
                .select_related('control', 'framework_version'))
    rows.sort(key=lambda r: (order.get(r.status, 9), r.control.control_id))
    return rows
