"""Phase 8G-RISK-REMEDIATION-A — deterministic Risk & Remediation engine.

Converts ControlGapAssessment rows (Phase 8F) into company RiskItem rows and a
system remediation RemediationTask per generated risk. Reuses the existing `risk`
app models — NO new model, NO migration.

Rules (deterministic; no AI, no final compliance decision, no certification):

    gap status            -> (likelihood, impact) -> severity (auto)     risk?
    missing               -> (4, 4) = 16          -> high                yes
    needs_review          -> (3, 3) =  9          -> medium              yes
    partially_compliant   -> (2, 2) =  4          -> low                 yes
    compliant             -> —                                            no (auto-mitigate existing)
    not_applicable        -> —                                            no (auto-mitigate existing)

Idempotent via the natural key (company, control, source='gap_analysis'):
re-running updates the deterministic fields but preserves the user's remediation
progress (risk status, owner, due date) once set.
"""
SOURCE = 'gap_analysis'
SYSTEM_TASK_TITLE = 'خطة معالجة أولية · Preliminary remediation plan'

# gap status -> (likelihood, impact, category, priority)
_GAP_MAP = {
    'missing':             (4, 4, 'other', 'high'),
    'needs_review':        (3, 3, 'other', 'medium'),
    'partially_compliant': (2, 2, 'other', 'low'),
}
RISK_GENERATING_STATUSES = set(_GAP_MAP)
_NO_RISK_STATUSES = {'compliant', 'not_applicable'}


def _remediation_guidance(gap):
    if gap.status == 'missing':
        return ('ارفع الأدلة المطلوبة لهذا الضابط ثم أعد حساب الجاهزية. '
                '· Upload the required evidence for this control, then recalculate readiness.')
    if gap.status == 'needs_review':
        return ('راجع الأدلة المرفوعة يدويًا أو أعد رفع مستند يحتوي نصًا قابلًا للاستخراج. '
                '· Review the uploaded evidence manually, or re-upload a document with extractable text.')
    return ('استكمل الأدلة ووثّق الضوابط للوصول إلى الجاهزية الكاملة (بانتظار مراجعة بشرية). '
            '· Complete the evidence and documentation toward full readiness (pending human review).')


def generate_risks_from_gap(company, actor=None):
    """Create/update RiskItems + remediation tasks from the company's gap rows.

    Returns a summary dict {created, updated, mitigated, severity_counts, total_open}.
    Idempotent; handles an empty company gracefully (no gap rows -> zeros, no error).
    Writes an audit entry (never blocks).
    """
    from compliance.gap_engine import gap_rows
    from .models import RiskItem, RemediationTask

    created = updated = mitigated = 0
    for gap in gap_rows(company):
        control = gap.control
        existing = RiskItem.objects.filter(company=company, control=control, source=SOURCE).first()

        if gap.status in _NO_RISK_STATUSES:
            # Control no longer a gap: auto-mitigate any open gap-sourced risk (never delete).
            if existing is not None and existing.is_open:
                existing.status = 'mitigated'
                existing.save(update_fields=['status', 'updated_at'])
                mitigated += 1
            continue

        likelihood, impact, category, priority = _GAP_MAP[gap.status]
        title = 'فجوة ضابط · Control gap: %s' % control.control_id
        description = gap.reason or ''

        if existing is None:
            risk = RiskItem.objects.create(
                company=company, control=control, source=SOURCE,
                framework_version=gap.framework_version, category=category,
                title=title, description=description,
                likelihood=likelihood, impact=impact, status='open',
                created_by=actor if getattr(actor, 'is_authenticated', False) else None)
            created += 1
        else:
            # Preserve the user's remediation progress (status/owner/due); refresh the
            # deterministic fields only.
            existing.framework_version = gap.framework_version
            existing.category = category
            existing.title = title
            existing.description = description
            existing.likelihood = likelihood
            existing.impact = impact
            # If a previously mitigated risk regressed to a gap, reopen it.
            if existing.status in ('mitigated', 'closed'):
                existing.status = 'open'
            existing.save()
            risk = existing
            updated += 1

        # Ensure exactly one system remediation task exists for this risk (idempotent).
        RemediationTask.objects.update_or_create(
            risk=risk, title=SYSTEM_TASK_TITLE,
            defaults=dict(company=company, description=_remediation_guidance(gap),
                          priority=priority),
        )

    summary = risk_generation_summary(company)
    summary['created'] = created
    summary['updated'] = updated
    summary['mitigated'] = mitigated
    _audit_risk_generation(actor, company, created, updated, mitigated, summary)
    return summary


def risk_generation_summary(company):
    """Read-only counts for the risk dashboard / CRM summary (never 500s)."""
    from .models import RiskItem
    from . import services
    risks = services.company_risks(company)
    sev = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    for r in risks.filter(status__in=RiskItem.OPEN_STATUSES):
        sev[r.severity] = sev.get(r.severity, 0) + 1
    counts = services.risk_dashboard_counts(company)
    return {
        'severity_counts': sev,
        'total_open': counts['open'],
        'high_critical': counts['high_critical'],
        'overdue_tasks': counts['overdue_tasks'],
        'total': counts['total'],
        'created': 0, 'updated': 0, 'mitigated': 0,
    }


def valid_task_statuses():
    """The existing RemediationTask status vocabulary (reused, not redefined)."""
    from .models import RemediationTask
    return {k for k, _ in RemediationTask.STATUS_CHOICES}


def set_task_status(company, task, status, actor=None):
    """POST-only helper: update a remediation task's status (tenant-safe, audited).

    Returns True if changed. Raises ValueError for an invalid status.
    """
    if status not in valid_task_statuses():
        raise ValueError('invalid status')
    old = task.status
    task.status = status
    task.save()  # model.save() handles completed_at for 'done'
    _audit_remediation(actor, company, task, old, status)
    return True


def _audit_risk_generation(actor, company, created, updated, mitigated, summary):
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action='risk_generated_from_gap',
            path='/compliance/risks/',
            metadata={
                'company_id': getattr(company, 'id', None),
                'risks_created': created, 'risks_updated': updated, 'risks_mitigated': mitigated,
                'severity_counts': summary.get('severity_counts', {}),
                'total_open': summary.get('total_open', 0),
                'performed_by': getattr(actor, 'email', ''),
            },
        )
    except Exception:
        pass


def _audit_remediation(actor, company, task, old_status, new_status):
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action='remediation_status_changed',
            path='/compliance/risks/',
            metadata={
                'company_id': getattr(company, 'id', None),
                'task_id': getattr(task, 'id', None),
                'risk_id': getattr(task, 'risk_id', None),
                'old_status': old_status, 'new_status': new_status,
                'performed_by': getattr(actor, 'email', ''),
            },
        )
    except Exception:
        pass
