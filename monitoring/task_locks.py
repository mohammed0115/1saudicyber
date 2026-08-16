"""Small cache-backed distributed leases for scheduled monitoring work."""
from __future__ import annotations

import secrets
from contextlib import contextmanager

from django.core.cache import cache


@contextmanager
def task_lease(name, timeout=900):
    """Yield True only to the worker that acquired the named lease.

    Redis ``add`` is atomic. The random token prevents one slow task from
    deleting a lease that was later acquired by a different worker.
    """
    key = f'cyber5:task-lease:{name}'
    token = secrets.token_urlsafe(18)
    acquired = cache.add(key, token, timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired and cache.get(key) == token:
            cache.delete(key)
