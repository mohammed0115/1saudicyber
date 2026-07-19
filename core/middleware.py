"""
Custom middleware:
  - ContentSecurityPolicyMiddleware: adds a CSP header (NFR-017).
  - AuditLogMiddleware: records authenticated, state-changing actions (FR-012.8 / NFR-021).
"""
from django.conf import settings

# Paths we never log (noise / static).
_SKIP_PREFIXES = ('/static/', '/media/', '/favicon')
# Only these methods change state and are worth auditing.
_AUDIT_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, 'CONTENT_SECURITY_POLICY', '')
        if policy and 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = policy
            response['X-Content-Type-Options'] = 'nosniff'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response


class EnforceAdminMFAMiddleware:
    """DD-fix: when settings.ENFORCE_ADMIN_MFA is on, a staff/admin user who has not
    enabled MFA is redirected to the MFA setup page before reaching any other view.

    Opt-in (default off) so existing deployments are unaffected until they choose to
    require it. Exempts the auth/MFA/logout/static paths so the user can actually set it up.
    """
    _EXEMPT = ('/login', '/logout', '/mfa/', '/static/', '/media/', '/healthz', '/i18n/',
               '/password-reset', '/reset/', '/invite/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'ENFORCE_ADMIN_MFA', False):
            user = getattr(request, 'user', None)
            if (user is not None and user.is_authenticated
                    and (user.is_staff or user.is_superuser)
                    and not getattr(user, 'mfa_enabled', False)
                    and not request.path.startswith(self._EXEMPT)):
                from django.shortcuts import redirect
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
            # Auditing must never break the request.
            pass
        return response

    def _maybe_log(self, request, response):
        path = request.path
        if request.method not in _AUDIT_METHODS:
            return
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return
        from core.models import AuditLog
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(
            user=user,
            company=getattr(user, 'company', None),
            method=request.method,
            path=path[:300],
            status_code=getattr(response, 'status_code', 0),
            ip_address=ip or None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
        )
