"""Central account and request-security policy for web and API entry points."""
from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings

MFA_REQUIRED_ROLES = frozenset({'admin', 'company_admin', 'auditor'})


def mfa_required(user) -> bool:
    """Return whether a user must complete MFA before accessing protected data."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(
        getattr(user, 'is_staff', False)
        or getattr(user, 'is_superuser', False)
        or getattr(user, 'role', '') in MFA_REQUIRED_ROLES
    )


def account_ready_for_access(user) -> bool:
    """A protected endpoint requires an authenticated, email-verified account."""
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'email_verified', False)
    )


def trusted_client_ip(request) -> str | None:
    """Honor X-Forwarded-For only when the direct peer is a configured proxy."""
    direct_peer = (request.META.get('REMOTE_ADDR') or '').strip()
    trusted_proxies = set(getattr(settings, 'TRUSTED_PROXY_IPS', ()))
    if direct_peer and direct_peer in trusted_proxies:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',', 1)[0].strip() or direct_peer
    return direct_peer or None


def safe_next_url(request, default: str = '/dashboard/') -> str:
    """Keep post-auth redirects local to this application."""
    candidate = (request.GET.get('next') or request.POST.get('next') or '').strip()
    if not candidate:
        return default
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith('/') or candidate.startswith('//'):
        return default
    return candidate
