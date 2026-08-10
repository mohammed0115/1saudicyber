"""Phase 8H-REPORTING-A — Commercial (internal readiness) Report Engine.

Aggregates existing deterministic engines into ONE internal readiness report:
  * gap_engine (Phase 8F) — per-control readiness + framework readiness %
  * risk_engine / risk app (Phase 8G) — risks + remediation
  * evidence submissions + text extraction (Phase 8E)

This report is INTERNAL and PRELIMINARY. It is NOT an official certification and
NOT a government accreditation, and it always requires human review. Read-only
aggregation — no AI, no writes, no compliance-status changes.
"""


def evidence_report_summary(company):
    """Uploaded / extracted / manual-review / failed counts (read-only, never 500s)."""
    summary = {'uploaded': 0, 'extracted': 0, 'manual_review': 0, 'failed': 0}
    try:
        from .models import EvidenceSubmission, EvidenceTextExtraction
        summary['uploaded'] = EvidenceSubmission.objects.filter(company=company).count()
        ext = EvidenceTextExtraction.objects.filter(submission__company=company)
        summary['extracted'] = ext.filter(status='extracted', char_count__gt=0).count()
        summary['failed'] = ext.filter(status='failed').count()
        summary['manual_review'] = ext.filter(
            status__in=['no_text_extracted', 'unsupported_type', 'too_large']).count()
    except Exception:
        pass
    return summary


def framework_readiness_summary(company):
    """Per-framework readiness (reuses the Phase 8F gap engine)."""
    from .gap_engine import get_company_gap_summary
    return get_company_gap_summary(company)


def gap_report_summary(company):
    """Open-gap rows (missing / needs_review / partially_compliant) with reasons."""
    from .gap_engine import gap_rows
    rows = [r for r in gap_rows(company)
            if r.status in ('missing', 'needs_review', 'partially_compliant')]
    return {
        'rows': rows,
        'missing': sum(1 for r in rows if r.status == 'missing'),
        'needs_review': sum(1 for r in rows if r.status == 'needs_review'),
        'partially_compliant': sum(1 for r in rows if r.status == 'partially_compliant'),
        'total': len(rows),
    }


def risk_report_summary(company):
    """Risks by severity/status + high/critical list + accepted/mitigated counts."""
    from risk.models import RiskItem
    from risk import services as risk_services
    risks = list(risk_services.company_risks(company).select_related('control'))
    sev = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    status = {}
    for r in risks:
        if r.is_open:
            sev[r.severity] = sev.get(r.severity, 0) + 1
        status[r.status] = status.get(r.status, 0) + 1
    high_critical = [r for r in risks if r.is_open and r.severity in ('high', 'critical')]
    return {
        'total': len(risks),
        'severity_counts': sev,
        'status_counts': status,
        'high_critical': high_critical,
        'open': sum(1 for r in risks if r.is_open),
        'accepted': status.get('accepted', 0),
        'mitigated': status.get('mitigated', 0) + status.get('closed', 0),
    }


def remediation_report_summary(company):
    """Remediation tasks with status/priority/due/linked risk (read-only)."""
    from django.utils import timezone
    from risk.models import RemediationTask
    tasks = list(RemediationTask.objects.filter(company=company)
                 .select_related('risk', 'risk__control').order_by('due_date'))
    today = timezone.now().date()
    overdue = sum(1 for t in tasks
                  if t.due_date and t.due_date < today and t.status not in ('done', 'cancelled'))
    status = {}
    for t in tasks:
        status[t.status] = status.get(t.status, 0) + 1
    return {'tasks': tasks, 'total': len(tasks), 'overdue': overdue, 'status_counts': status}


def _next_actions(readiness, gap, risk, remediation):
    """Deterministic, safe next-recommended-actions list (bilingual)."""
    actions = []
    if gap['missing']:
        actions.append('ارفع الأدلة المطلوبة لـ %d ضابط ناقص. · Upload evidence for %d missing controls.'
                       % (gap['missing'], gap['missing']))
    if gap['needs_review']:
        actions.append('راجع %d ضابطًا فيه أدلة دون نص قابل للاستخراج. · Review %d controls with evidence but no readable text.'
                       % (gap['needs_review'], gap['needs_review']))
    if risk['high_critical']:
        actions.append('عالج %d خطرًا عالي/حرج. · Address %d high/critical risks.'
                       % (len(risk['high_critical']), len(risk['high_critical'])))
    if remediation['overdue']:
        actions.append('أكمل %d مهمة معالجة متأخرة. · Complete %d overdue remediation tasks.'
                       % (remediation['overdue'], remediation['overdue']))
    if not actions:
        actions.append('حافظ على الجاهزية واطلب مراجعة المدقق الداخلي. · Maintain readiness and request internal auditor review.')
    return actions


def build_commercial_readiness_report(company):
    """Assemble the full internal readiness report (read-only). Never 500s when empty."""
    from django.utils import timezone
    fr = framework_readiness_summary(company)
    ev = evidence_report_summary(company)
    gap = gap_report_summary(company)
    risk = risk_report_summary(company)
    rem = remediation_report_summary(company)

    overall = fr.get('overall', {})
    executive = {
        'company': company,
        'report_date': timezone.now(),
        'frameworks': fr.get('frameworks', []),
        'overall_readiness_percent': fr.get('overall_readiness_percent', 0),
        'controls_assessed': fr.get('total', 0),
        'counts': overall,
        'open_risks': risk['open'],
        'high_critical_risks': len(risk['high_critical']),
        'overdue_tasks': rem['overdue'],
    }
    return {
        'company': company,
        'executive': executive,
        'framework_readiness': fr.get('frameworks', []),
        'evidence': ev,
        'gap': gap,
        'risk': risk,
        'remediation': rem,
        'next_actions': _next_actions(executive, gap, risk, rem),
        'has_data': fr.get('total', 0) > 0 or ev['uploaded'] > 0 or risk['total'] > 0,
    }


def record_report_audit(actor, company, report, action='viewed'):
    """Audit a report view/refresh via core.AuditLog (never blocks)."""
    try:
        from core.models import AuditLog
        ex = report.get('executive', {}) if isinstance(report, dict) else {}
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=f'report_{action}'[:100],
            path='/compliance/reports/commercial-readiness/',
            metadata={
                'company_id': getattr(company, 'id', None),
                'report_type': 'commercial_readiness',
                'readiness_percent': ex.get('overall_readiness_percent', 0),
                'framework_count': len(ex.get('frameworks', [])),
                'performed_by': getattr(actor, 'email', ''),
            },
        )
    except Exception:
        pass
