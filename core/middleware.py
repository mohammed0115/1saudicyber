"""
Custom middleware:
  - ContentSecurityPolicyMiddleware: adds a CSP header (NFR-017).
  - AuditLogMiddleware: records authenticated, state-changing actions (FR-012.8 / NFR-021).
"""
import time
import uuid

from django.conf import settings

# Paths we never log (noise / static).
_SKIP_PREFIXES = ('/static/', '/media/', '/favicon')
# Only these methods change state and are worth auditing.
_AUDIT_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class CorrelationIdMiddleware:
    """Attach a stable correlation ID and latency header to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.META.get('HTTP_X_REQUEST_ID', '')
        try:
            trace_id = str(uuid.UUID(supplied))
        except (ValueError, TypeError, AttributeError):
            trace_id = str(uuid.uuid4())
        request.trace_id = trace_id
        started = time.perf_counter()
        response = self.get_response(request)
        response['X-Request-ID'] = trace_id
        response['X-Response-Time-ms'] = str(round((time.perf_counter() - started) * 1000, 2))
        return response


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
            metadata={'trace_id': getattr(request, 'trace_id', '')},
        )
