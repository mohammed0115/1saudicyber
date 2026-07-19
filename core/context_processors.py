"""Template context processors — expose the in-app notification unread count to the nav."""
from .notify_services import unread_count


def notifications(request):
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return {'nav_unread': 0}
    try:
        return {'nav_unread': unread_count(user)}
    except Exception:
        return {'nav_unread': 0}
