"""In-app notification helpers. Creates core.Notification rows (best-effort).

Never raises into the caller's request path — notification failures must not break
the underlying action (RFI, verdict, assignment, ...).
"""
from .models import Notification


def notify(recipient, title, *, body='', url='', kind='system'):
    """Create one in-app notification. Returns it, or None on failure."""
    if recipient is None:
        return None
    try:
        return Notification.objects.create(
            recipient=recipient, kind=kind, title=title[:200], body=(body or '')[:500],
            url=(url or '')[:300])
    except Exception:
        return None


def notify_many(recipients, title, *, body='', url='', kind='system'):
    """Notify a list/queryset of users (deduplicated by id)."""
    seen = set()
    for r in recipients:
        if r is None or r.id in seen:
            continue
        seen.add(r.id)
        notify(r, title, body=body, url=url, kind=kind)


def unread_count(user):
    if not getattr(user, 'is_authenticated', False):
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()
