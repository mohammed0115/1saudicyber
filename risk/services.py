"""Phase 5A — risk register service (deterministic, tenant-safe, read-only helpers)."""
from datetime import date

from .models import RiskItem, RemediationTask


def company_risks(company):
    return RiskItem.objects.filter(company=company)


def company_tasks(company):
    return RemediationTask.objects.filter(company=company)


def get_company_risk(company, risk_id):
    """Tenant-safe single-risk lookup or None."""
    if not company:
        return None
    return RiskItem.objects.filter(id=risk_id, company=company).first()


def get_company_task(company, task_id):
    if not company:
        return None
    return RemediationTask.objects.filter(id=task_id, company=company).first()


def auditor_can_view_company_risks(user, company):
    """True only for an ACTIVE auditor with an ACCEPTED assignment to this company."""
    from auditors.models import AuditorAssignment
    return AuditorAssignment.objects.filter(
        auditor__user=user, auditor__status='active',
        company=company, status='accepted').exists()


def risk_dashboard_counts(company):
    """Read-only counts for dashboards. Never writes."""
    risks = company_risks(company)
    open_risks = risks.filter(status__in=RiskItem.OPEN_STATUSES)
    high_critical = open_risks.filter(severity__in=['high', 'critical']).count()
    overdue_tasks = company_tasks(company).filter(
        due_date__lt=date.today()).exclude(status__in=['done', 'cancelled']).count()
    return {
        'open': open_risks.count(),
        'high_critical': high_critical,
        'overdue_tasks': overdue_tasks,
        'mitigated': risks.filter(status__in=['mitigated', 'closed']).count(),
        'total': risks.count(),
    }


def has_open_high_critical(company):
    return company_risks(company).filter(
        status__in=RiskItem.OPEN_STATUSES, severity__in=['high', 'critical']).exists()
