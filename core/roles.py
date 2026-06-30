"""Phase 8D-3C-SECURITY-A — canonical role/portal helpers + guards.

One place that answers "which portal does this user belong to?", so views and
templates stop making implicit assumptions (e.g. treating a staff/auditor account
as a customer). Read-only; no models, no migrations. Reuses existing helpers
(auditors.services.get_auditor_profile, auditors.admin_services.is_platform_admin).

Portal keys returned by portal_for():
    'platform_admin' | 'auditor' | 'company' | 'company_unlinked' | 'anonymous'
"""
from functools import wraps

from django.shortcuts import render, redirect


def is_platform_admin_user(user):
    """Get Solution staff: authenticated staff or superuser."""
    return bool(getattr(user, 'is_authenticated', False)
                and (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)))


def get_auditor_profile(user):
    """The user's AuditorProfile or None (never raises)."""
    if not getattr(user, 'is_authenticated', False):
        return None
    from auditors.services import get_auditor_profile as _gap
    return _gap(user)


def is_auditor_user(user):
    """True if the user has an auditor profile (any status)."""
    return get_auditor_profile(user) is not None


def get_user_company(user):
    """The user's linked Company or None."""
    if not getattr(user, 'is_authenticated', False):
        return None
    return getattr(user, 'company', None)


def is_company_user(user):
    """A customer-portal user: authenticated, NOT staff, NOT auditor, with a company."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if is_platform_admin_user(user) or is_auditor_user(user):
        return False
    return get_user_company(user) is not None


def portal_for(user):
    """Classify the user into exactly one portal key. Order matters (fail-closed)."""
    if not getattr(user, 'is_authenticated', False):
        return 'anonymous'
    if is_platform_admin_user(user):
        return 'platform_admin'
    if is_auditor_user(user):
        return 'auditor'
    if get_user_company(user) is not None:
        return 'company'
    return 'company_unlinked'


def anonymous_only(view):
    """Registration guard: authenticated users get a safe 'already signed in' page
    instead of silently creating/switching account context. Anonymous users pass through.
    """
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'is_authenticated', False):
            return render(request, 'core/already_authenticated.html',
                          {'portal': portal_for(request.user)}, status=200)
        return view(request, *args, **kwargs)
    return _wrapped
