"""
DD-fix — cache-based brute-force throttle for the HTML login form.

The DRF throttles only cover the API; the session `/login/` view had no protection.
This uses the Django cache (Redis in prod, locmem in dev) to count recent failures per
(username + client IP) and lock the pair out after LOGIN_FAILURE_LIMIT within
LOGIN_FAILURE_WINDOW seconds. No extra dependency.
"""
from django.conf import settings
from django.core.cache import cache


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or 'unknown'


def _key(username, request):
    return 'loginfail:%s:%s' % ((username or '').lower().strip()[:120], _client_ip(request))


def is_locked(username, request):
    """True if this (username, IP) has exceeded the failure limit within the window."""
    limit = getattr(settings, 'LOGIN_FAILURE_LIMIT', 8)
    return cache.get(_key(username, request), 0) >= limit


def record_failure(username, request):
    """Increment the failure counter (resets the TTL window on each failure)."""
    window = getattr(settings, 'LOGIN_FAILURE_WINDOW', 900)
    key = _key(username, request)
    try:
        count = cache.get(key, 0) + 1
        cache.set(key, count, window)
        return count
    except Exception:
        return 0


def clear(username, request):
    """Clear the counter after a successful login."""
    try:
        cache.delete(_key(username, request))
    except Exception:
        pass
