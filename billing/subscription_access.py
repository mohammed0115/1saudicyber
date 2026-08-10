"""
Phase 4B — deterministic, tenant-safe subscription access service.

No payment provider, no external API, no secrets. Operates only on the company
passed in. Used by the report views/exports to gate access.
"""
from datetime import timedelta

from django.utils import timezone

from .models import CompanySubscription


def get_company_subscription(company):
    """Return the company's subscription, or None. Tenant-safe (single company)."""
    if not company:
        return None
    return CompanySubscription.objects.filter(company=company).first()


def ensure_company_subscription(company):
    """Get-or-create an (inactive by default) subscription row for the company."""
    if not company:
        return None
    sub, _ = CompanySubscription.objects.get_or_create(company=company)
    return sub


def company_has_active_subscription(company):
    """True only when the company has an active/trial subscription that has not ended."""
    sub = get_company_subscription(company)
    return bool(sub and sub.is_active())


def activate_company_subscription(company, plan_name, activated_by=None, days=30):
    """Manually activate (or extend) a company's subscription. Idempotent.

    No payment is taken; this is admin/manual activation only.
    """
    if not company:
        return None
    sub = ensure_company_subscription(company)
    now = timezone.now()
    sub.status = 'active'
    sub.plan_name = plan_name or sub.plan_name or 'Standard'
    sub.starts_at = sub.starts_at or now
    sub.ends_at = now + timedelta(days=days) if days else None
    if activated_by is not None:
        sub.activated_by = activated_by
    sub.save()
    return sub


def expire_company_subscription(company):
    """Mark a company's subscription expired (no report download/export)."""
    sub = get_company_subscription(company)
    if sub:
        sub.status = 'expired'
        sub.save(update_fields=['status', 'updated_at'])
    return sub


def can_view_full_reports(company):
    """Whether the company may view full on-screen reports."""
    return company_has_active_subscription(company)


def can_export_reports(company):
    """Whether the company may download/export reports (CSV/XLSX)."""
    sub = get_company_subscription(company)
    return bool(sub and sub.is_active() and sub.report_exports_allowed)
