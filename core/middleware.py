"""Security headers, account-access gates, and audit logging middleware."""
from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

from core.security import account_ready_for_access, mfa_required, trusted_client_ip

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = ('/static/', '/media/', '/favicon')
_AUDIT_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)
        policy = getattr(settings, 'CONTENT_SECURITY_POLICY', '').replace('{NONCE}', request.csp_nonce)
        if policy and 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = policy
            response['X-Content-Type-Options'] = 'nosniff'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
            response['Cross-Origin-Opener-Policy'] = 'same-origin'
        return response


class EnforceAccountVerificationMiddleware:
    """Keep unverified accounts inside the email-verification journey only."""

    _EXEMPT = (
        '/logout', '/verify-email/', '/mfa/', '/static/', '/media/', '/healthz',
        '/readyz', '/i18n/', '/privacy/', '/terms/', '/password-reset', '/reset/',
        '/invite/', '/registration-complete/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not account_ready_for_access(user):
            if request.path.startswith('/api/'):
                return JsonResponse(
                    {'detail': 'يجب تأكيد البريد الإلكتروني قبل استخدام الواجهة البرمجية.'},
                    status=403,
                )
            if not request.path.startswith(self._EXEMPT):
                return redirect('core:verify_email_otp')
        return self.get_response(request)


class EnforceAdminMFAMiddleware:
    """Require MFA for platform staff and business-sensitive roles."""

    _EXEMPT = (
        '/login', '/logout', '/verify-email/', '/mfa/', '/static/', '/media/', '/healthz',
        '/readyz', '/i18n/', '/privacy/', '/terms/', '/password-reset', '/reset/', '/invite/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'ENFORCE_ADMIN_MFA', False):
            user = getattr(request, 'user', None)
            if (
                account_ready_for_access(user)
                and mfa_required(user)
                and not getattr(user, 'mfa_enabled', False)
                and not request.path.startswith(self._EXEMPT)
            ):
                if request.path.startswith('/api/'):
                    return JsonResponse(
                        {'detail': 'تتطلب هذه الحسابات مصادقة متعددة العوامل عبر بوابة الويب.'},
                        status=403,
                    )
                return redirect('core:mfa_setup')
        return self.get_response(request)


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_log(request, response)
        except Exception:
            # Telemetry failure must not break the request, but must remain observable.
            logger.exception('تعذر تسجيل عملية تدقيق')
        return response

    def _maybe_log(self, request, response):
        path = request.path
        if request.method not in _AUDIT_METHODS:
            return
        if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return
        from core.models import AuditLog

        AuditLog.objects.create(
            user=user,
            company=getattr(user, 'company', None),
            method=request.method,
            path=path[:300],
            status_code=getattr(response, 'status_code', 0),
            ip_address=trusted_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
        )
