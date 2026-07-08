"""Phase 8D-3C-SECURITY-A — canonical role/portal helpers + guards.

One place that answers "which portal does this user belong to?", so views and
templates stop making implicit assumptions (e.g. treating a staff/auditor account
as a customer). Read-only; no models, no migrations. Reuses existing helpers
(auditors.services.get_auditor_profile, auditors.admin_services.is_platform_admin).

Portal keys returned by portal_for():
    'platform_admin' | 'auditor' | 'company' | 'company_unlinked' | 'anonymous'
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
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


# ----------------------------------------------------------------------------
# Phase 8D-3C-B — explicit portal guards (defense-in-depth).
# These FRONT-LOAD the role checks the views previously did implicitly. They
# preserve existing behaviour exactly: a company-linked user (even staff) passes;
# a company-less user gets the role-aware no-company page (staff -> CRM message,
# auditor -> auditor portal, otherwise -> contact support).
# ----------------------------------------------------------------------------
def company_portal_guard(request):
    """Return None if the request may proceed as a company-portal user, else a
    safe HttpResponse (login redirect / role-aware no-company page)."""
    user = request.user
    if not getattr(user, 'is_authenticated', False):
        return redirect_to_login(request.get_full_path())
    # A linked company (even for a staff user acting in company context) is allowed.
    if get_user_company(user) is not None:
        return None
    # No company: the role-aware page explains the right portal (no raw confusion).
    return render(request, 'dashboard/no_company.html', status=200)


def company_portal_required(view):
    """Explicitly require a company-linked user for a company/compliance view."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        blocked = company_portal_guard(request)
        if blocked is not None:
            return blocked
        return view(request, *args, **kwargs)
    return _wrapped


def auditor_portal_guard(request, *, require_active=False):
    """Return None if the request may proceed as an auditor-portal user, else a
    safe HttpResponse. Preserves the existing 'no profile -> auditor registration'
    flow for company/unlinked users; staff/superuser get a safe portal-mismatch page.
    """
    user = request.user
    if not getattr(user, 'is_authenticated', False):
        return redirect_to_login(request.get_full_path())
    profile = get_auditor_profile(user)
    if profile is None:
        if is_platform_admin_user(user):
            return render(request, 'core/portal_mismatch.html',
                          {'target': 'platform_admin'}, status=200)
        # Company / unlinked user: keep the existing safe redirect to auditor sign-up
        # (which itself blocks an authenticated non-auditor from switching session).
        return redirect('auditors:register')
    if require_active and not profile.is_active_auditor:
        # Pending/suspended auditor on an operational page -> their status page.
        return redirect('auditors:onboarding')
    return None


def email_verification_guard(request):
    """Return None if the user may perform a compliance-affecting action, else a safe
    response. UNVERIFIED company users are blocked from sensitive actions (evidence upload,
    submit-to-auditor, final reports) — they may still browse onboarding/intake/classification.
    Internal staff/superusers are trusted and pass through.
    """
    from django.contrib import messages
    user = request.user
    if not getattr(user, 'is_authenticated', False):
        return redirect_to_login(request.get_full_path())
    if is_platform_admin_user(user):
        return None
    if getattr(user, 'email_verified', False):
        return None
    messages.error(request, 'يرجى التحقق من بريدك الإلكتروني قبل تنفيذ هذه العملية.')
    return redirect('core:onboarding')


def email_verified_required(view):
    """Guard a sensitive company action behind email verification (fail-closed)."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        blocked = email_verification_guard(request)
        if blocked is not None:
            return blocked
        return view(request, *args, **kwargs)
    return _wrapped


def auditor_portal_required(view=None, *, require_active=False):
    """Explicitly require a valid auditor profile for an auditor-portal view.

    Use require_active=True for pages that must not be reached by a pending auditor.
    """
    def _decorate(v):
        @wraps(v)
        def _wrapped(request, *args, **kwargs):
            blocked = auditor_portal_guard(request, require_active=require_active)
            if blocked is not None:
                return blocked
            return v(request, *args, **kwargs)
        return _wrapped
    return _decorate(view) if view is not None else _decorate
