"""P0-01 — central object-level (tenant) authorization helpers.

The project already has *portal/role* guards in ``core.roles`` (which portal a user
belongs to). This module adds the missing *object-level* layer: fetch-or-404 an object
ONLY when it belongs to the caller's company, so a valid-but-foreign id can never be
reached — regardless of hidden buttons, edited POST bodies, or guessed ids.

Design principles:
  * Never trust a client-supplied id. Scope the query, don't filter the result.
  * Return 404 (not 403) for a foreign/nonexistent object so existence isn't leaked.
  * Ownership is expressed as a Django lookup so it works for a direct ``company`` FK
    (default) or a relation path like ``company_control__company``.
  * A user with no company owns nothing → Http404.
  * Multi-model operations must prove every object shares one company (``same_company``).

These are deliberately small and composable; they complement — never replace — the
existing service helpers (e.g. ``risk.services.get_company_risk``).
"""
from django.http import Http404
from django.shortcuts import get_object_or_404


def company_scoped_qs(model, company, *, company_lookup='company', **filters):
    """Objects of `model` owned by `company`. Empty queryset if company is falsy."""
    if not company:
        return model.objects.none()
    return model.objects.filter(**{company_lookup: company}, **filters)


def get_company_scoped_object(model, company, *, company_lookup='company', **lookups):
    """Fetch one `model` instance owned by `company`, or raise Http404.

    `lookups` are the remaining filters (typically ``pk=...`` / ``id=...``). Ownership is
    enforced inside the query — a foreign id simply doesn't match and yields 404.
    """
    if not company:
        raise Http404('No company context.')
    return get_object_or_404(model, **{company_lookup: company}, **lookups)


def _company_id_of(obj, attr='company'):
    """Resolve an object's owning company id via a possibly nested attr path
    (e.g. 'company' or 'company_control__company'). Returns None if unresolved."""
    if obj is None:
        return None
    # Fast path: a direct company_id FK column.
    direct = getattr(obj, f'{attr}_id', None)
    if direct is not None:
        return direct
    cur = obj
    for part in attr.replace('__', '.').split('.'):
        cur = getattr(cur, part, None)
        if cur is None:
            return None
    return getattr(cur, 'id', cur)


def same_company(*objs, company_attr='company'):
    """True iff every object resolves to the SAME non-null company id.

    Use before any multi-model write (e.g. linking an AuditNote's assessment and
    company_control) so a request can't stitch together objects from two tenants.
    Each entry may be an object or a (obj, attr) pair to override the ownership path.
    """
    ids = set()
    for entry in objs:
        if isinstance(entry, tuple):
            obj, attr = entry
        else:
            obj, attr = entry, company_attr
        cid = _company_id_of(obj, attr)
        if cid is None:
            return False
        ids.add(cid)
    return len(ids) == 1


def assert_same_company(*objs, company_attr='company'):
    """Raise Http404 unless all objects share one company (fail-closed for writes)."""
    if not same_company(*objs, company_attr=company_attr):
        raise Http404('Cross-company object mismatch.')
