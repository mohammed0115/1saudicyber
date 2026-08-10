"""
Phase 3J — small, additive security helpers + documented assumptions.

Security assumptions for the CyberTrust workflow (intake -> framework approval ->
control plan -> evidence checklist -> upload v2 -> advisory analysis -> auditor
review -> reports -> journey dashboard):

1. Authentication: every workflow view is decorated with @login_required.
2. Tenant isolation: every company-scoped object is fetched with an explicit
   ``company=request.user.company`` filter. No view fetches a company-scoped
   object by primary key alone. Use :func:`get_company_object_or_none` for that.
3. Staff-only mutations: generating scopes/plans/checklists/assessments,
   triggering advisory analysis, and updating a ControlAssessment all require
   ``request.user.is_staff``. Read pages are open to the owning company's users.
4. AI is advisory only: analysis never creates/updates a ControlAssessment and
   never sets a compliance status. The auditor's decision is the only source of
   truth. Reports read ControlAssessment status only; unreviewed controls are
   never counted as compliant; legacy (non-official) controls and CompanyControl
   are never used by the reporting/assessment pipeline.

These helpers are additive and do not change any existing behavior.
"""


def get_company_object_or_none(model, company, **filters):
    """Tenant-safe single-object lookup.

    Returns the first ``model`` instance matching ``company`` AND ``filters``,
    or ``None``. Never returns an object owned by another company, and returns
    ``None`` when ``company`` is falsy (e.g. a user with no company).
    """
    if not company:
        return None
    return model.objects.filter(company=company, **filters).first()


def user_is_staff(user):
    """True only for authenticated staff/auditor users (gate for staff-only actions)."""
    return bool(getattr(user, 'is_authenticated', False) and getattr(user, 'is_staff', False))
