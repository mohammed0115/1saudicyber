"""Central company-tenant boundary for application and API code.

All company-owned queries must enter through ``scoped_queryset`` (or a model
manager exposing ``for_company``) rather than accepting arbitrary identifiers.
The legacy ``User.company`` field remains supported during the membership
migration, but new callers resolve the active company here.
"""
from __future__ import annotations

from typing import Type

from django.core.exceptions import PermissionDenied
from django.db import models


class TenantScopeError(PermissionDenied):
    """Raised when a request has no active company tenant."""


class CompanyScopedQuerySet(models.QuerySet):
    """Reusable queryset mixin for models with a direct ``company`` relation."""

    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class CompanyScopedManager(models.Manager.from_queryset(CompanyScopedQuerySet)):
    """Manager for direct company-owned models."""


# Relationship paths for company-owned resources that do not expose a direct
# ``company`` field. Keep this registry explicit so adding a new tenant model
# requires a deliberate architecture decision and code review.
_SCOPE_LOOKUPS: dict[str, str] = {
    "Company": "pk",
    "CompanyControl": "company",
    "ControlAssessment": "company",
    "EvidenceSubmission": "company",
    "Evidence": "company_control__company",
    "GapAnalysis": "company",
    "ComplianceScore": "company",
    "Alert": "company",
    "RiskItem": "company",
    "RemediationTask": "company",
    "Assessment": "company",
    "AuditLog": "company",
    "Payment": "company",
    "CompanySubscription": "company",
}


def active_company_for(user):
    """Resolve a user's active tenant with a safe legacy fallback.

    A primary active membership wins. Existing users created before the
    membership migration retain access through ``User.company`` until the
    backfill has completed.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        raise TenantScopeError("Authenticated company context is required.")
    memberships = getattr(user, "company_memberships", None)
    if memberships is not None:
        membership = (memberships.filter(is_active=True)
                      .select_related("company")
                      .order_by("-is_default", "id")
                      .first())
        if membership is not None:
            return membership.company
    company = getattr(user, "company", None)
    if company is not None:
        return company
    raise TenantScopeError("No active company is associated with this account.")


def scoped_queryset(model: Type[models.Model], company):
    """Return a queryset scoped to one company or fail closed for unknown models."""
    lookup = _SCOPE_LOOKUPS.get(model.__name__)
    if not lookup:
        raise TenantScopeError(
            f"Model {model.__name__} has no registered company scope; add it explicitly."
        )
    if model.__name__ == "Company":
        return model.objects.filter(pk=company.pk)
    return model.objects.filter(**{lookup: company})


def require_company_for(user):
    """Alias used by request handlers to make the tenant boundary obvious."""
    return active_company_for(user)
