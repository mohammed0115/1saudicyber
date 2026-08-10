"""
Phase 5B — Continuous Monitoring service layer (deterministic, internal-only).

NO external network calls, NO AI/LLM, NO changes to ControlAssessment decisions.
A monitoring run only READS company data and writes MonitoringRun/MonitoringFinding
records and the check's schedule fields.
"""
from datetime import date, timedelta

from django.utils import timezone

from .models import MonitoringCheck, MonitoringRun, MonitoringFinding

_FREQ_DAYS = {
    'daily': 1, 'weekly': 7, 'monthly': 30,
    'quarterly': 90, 'semi_annual': 182, 'annual': 365,
}
# Evidence is considered "fresh enough" within one cycle of the check frequency.
_FRESHNESS_DAYS = dict(_FREQ_DAYS)

# Result -> finding severity by check type (deterministic).
_SEVERITY = {
    'risk_review': 'high',
    'control_status_review': 'high',
    'remediation_overdue': 'medium',
    'evidence_freshness': 'medium',
    'policy_review': 'low',
    'manual_review': 'low',
}


def calculate_next_run_at(frequency, from_dt=None):
    """Deterministic next-run datetime = from_dt + frequency window."""
    from_dt = from_dt or timezone.now()
    return from_dt + timedelta(days=_FREQ_DAYS.get(frequency, 30))


def _evaluate(check, now):
    """Return (status, summary, details, snapshot) for a check. READ-ONLY."""
    company = check.company
    if check.check_type == 'remediation_overdue':
        from risk.models import RemediationTask
        qs = RemediationTask.objects.filter(company=company, due_date__lt=date.today()).exclude(
            status__in=['done', 'cancelled'])
        if check.control_assessment_id:
            qs = qs.filter(risk__control_assessment_id=check.control_assessment_id)
        n = qs.count()
        if n:
            return 'fail', f'{n} مهمة معالجة متأخرة', 'توجد مهام معالجة تجاوزت تاريخ الاستحقاق.', {'overdue_tasks': n}
        return 'pass', 'لا مهام معالجة متأخرة', '', {'overdue_tasks': 0}

    if check.check_type == 'risk_review':
        from risk.models import RiskItem
        n = RiskItem.objects.filter(
            company=company, status__in=RiskItem.OPEN_STATUSES,
            severity__in=['high', 'critical']).count()
        if n:
            return 'needs_review', f'{n} خطر عالٍ/حرج مفتوح', 'مخاطر عالية/حرجة تتطلب مراجعة.', {'open_high_critical': n}
        return 'pass', 'لا مخاطر عالية/حرجة مفتوحة', '', {'open_high_critical': 0}

    if check.check_type == 'evidence_freshness':
        from compliance.models import EvidenceSubmission
        qs = EvidenceSubmission.objects.filter(company=company)
        if check.control_id:
            qs = qs.filter(checklist_item__evidence_requirement__control_id=check.control_id)
        latest = qs.order_by('-uploaded_at').first()
        window = _FRESHNESS_DAYS.get(check.frequency, 30)
        if latest is None:
            return 'needs_review', 'لا يوجد دليل مرفوع', 'لم تُرفع أدلة بعد لهذا النطاق.', {'has_evidence': False}
        age_days = (now - latest.uploaded_at).days
        if age_days > window:
            return ('needs_review', f'دليل قديم ({age_days} يوم)',
                    'آخر دليل أقدم من نافذة التحديث المتوقّعة.', {'age_days': age_days, 'window': window})
        return 'pass', f'دليل حديث ({age_days} يوم)', '', {'age_days': age_days, 'window': window}

    if check.check_type == 'control_status_review':
        a = check.control_assessment
        if a is None:
            return 'needs_review', 'لا يوجد تقييم مرتبط', 'لا يوجد تقييم ضابط مرتبط بالفحص.', {}
        if a.status == 'compliant':
            return 'pass', 'الضابط مطابق', '', {'assessment_status': a.status}
        if a.status in ('non_compliant', 'partially_compliant', 'needs_more_evidence', 'not_reviewed'):
            return ('needs_review', f'حالة الضابط: {a.get_status_display()}',
                    'حالة التقييم تستدعي مراجعة.', {'assessment_status': a.status})
        return 'pass', f'حالة الضابط: {a.get_status_display()}', '', {'assessment_status': a.status}

    # policy_review / manual_review -> always a human review prompt.
    return ('needs_review', 'مراجعة دورية مطلوبة',
            'فحص يدوي/سياسة يتطلّب مراجعة بشرية دورية.', {'manual': True})


def run_monitoring_check(check, apply=False, now=None):
    """Evaluate a check. With apply=True, persist a MonitoringRun (+ finding) and reschedule.

    Returns a dict: {status, created_run, created_finding}. Never raises for a normal
    evaluation; evaluation errors are recorded as an 'error' run when apply=True.
    """
    now = now or timezone.now()
    try:
        status, summary, details, snapshot = _evaluate(check, now)
        err = False
    except Exception:  # defensive: monitoring must never crash the batch
        status, summary, details, snapshot, err = 'error', 'تعذّر تنفيذ الفحص', '', {}, True

    if not apply:
        return {'status': status, 'created_run': False, 'created_finding': False}

    run = MonitoringRun.objects.create(
        monitoring_check=check, company=check.company, status=status,
        summary=summary[:300], details=details, evidence_snapshot=snapshot or {},
        started_at=now, finished_at=timezone.now())

    created_finding = False
    if status in ('fail', 'needs_review'):
        sev = _SEVERITY.get(check.check_type, 'medium')
        if status == 'fail' and sev == 'low':
            sev = 'medium'
        MonitoringFinding.objects.create(
            monitoring_run=run, company=check.company, severity=sev,
            title=f'{check.get_check_type_display()}: {check.title}'[:255],
            description=summary, recommendation='راجِع البند يدويًا واتّخذ الإجراء المناسب.')
        created_finding = True

    # Reschedule (does NOT touch any ControlAssessment).
    check.last_run_at = now
    check.next_run_at = calculate_next_run_at(check.frequency, now)
    check.last_result = status if status != 'error' else 'needs_review'
    check.save(update_fields=['last_run_at', 'next_run_at', 'last_result', 'updated_at'])
    return {'status': status, 'created_run': True, 'created_finding': created_finding}


def due_checks(now=None, company=None, check_type=None):
    """Active checks that are due (next_run_at null or <= now). Tenant-safe filtering."""
    now = now or timezone.now()
    from django.db.models import Q
    qs = MonitoringCheck.objects.filter(status='active').filter(
        Q(next_run_at__isnull=True) | Q(next_run_at__lte=now))
    if company is not None:
        qs = qs.filter(company=company)
    if check_type:
        qs = qs.filter(check_type=check_type)
    return qs


def run_due_monitoring_checks(apply=False, now=None, company=None, check_type=None, limit=None):
    """Run all due checks. Returns a summary dict. Deterministic."""
    now = now or timezone.now()
    qs = due_checks(now=now, company=company, check_type=check_type).order_by('id')
    scanned_total = MonitoringCheck.objects.filter(status='active')
    if company is not None:
        scanned_total = scanned_total.filter(company=company)
    if check_type:
        scanned_total = scanned_total.filter(check_type=check_type)
    checks = list(qs[:limit] if limit else qs)
    runs = findings = errors = 0
    for c in checks:
        res = run_monitoring_check(c, apply=apply, now=now)
        if res['status'] == 'error':
            errors += 1
        if res['created_run']:
            runs += 1
        if res['created_finding']:
            findings += 1
    return {
        'scanned': scanned_total.count(),
        'due': len(checks),
        'runs_created': runs,
        'findings_created': findings,
        'errors': errors,
        'applied': bool(apply),
    }


def summarize_company_monitoring(company):
    """Read-only monitoring summary for dashboards. Never writes."""
    now = timezone.now()
    checks = MonitoringCheck.objects.filter(company=company)
    active = checks.filter(status='active')
    from django.db.models import Q
    due = active.filter(Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)).count()
    overdue = active.filter(next_run_at__lt=now).count()
    findings = MonitoringFinding.objects.filter(company=company)
    open_findings = findings.filter(status__in=MonitoringFinding.OPEN_STATUSES)
    last_run = checks.exclude(last_run_at__isnull=True).order_by('-last_run_at').first()
    next_due = active.exclude(next_run_at__isnull=True).order_by('next_run_at').first()
    return {
        'active_checks': active.count(),
        'due': due,
        'overdue': overdue,
        'failed': active.filter(last_result='fail').count(),
        'needs_review': active.filter(last_result='needs_review').count(),
        'open_findings': open_findings.count(),
        'critical_high_findings': open_findings.filter(severity__in=['high', 'critical']).count(),
        'last_run_at': last_run.last_run_at if last_run else None,
        'next_due_at': next_due.next_run_at if next_due else None,
        'last_result': last_run.last_result if last_run else 'not_run',
    }


def auditor_can_view_company_monitoring(user, company):
    """True only for an active auditor with an accepted assignment to this company."""
    from auditors.models import AuditorAssignment
    return AuditorAssignment.objects.filter(
        auditor__user=user, auditor__status='active',
        company=company, status='accepted').exists()
