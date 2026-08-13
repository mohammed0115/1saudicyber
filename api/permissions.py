"""Tenant-scoping helpers for the public platform API.

The existing Company model is the tenant root. These helpers intentionally reject
resource access when a caller has no company context or the resource belongs to
another company.
"""
from rest_framework.exceptions import PermissionDenied


def require_company(request):
    company = getattr(request.user, 'company', None)
    if company is None and not getattr(request.user, 'is_superuser', False):
        raise PermissionDenied('A company tenant is required for this operation.')
    return company


def require_company_resource(request, resource, *, company_path='company'):
    """Verify that a resource resolves to the caller’s Company tenant."""
    company = require_company(request)
    if company is None:  # superuser; explicit administration is allowed
        return resource

    target = resource
    for attribute in company_path.split('.'):
        target = getattr(target, attribute, None)
        if target is None:
            raise PermissionDenied('The resource has no tenant ownership path.')
    if target.pk != company.pk:
        raise PermissionDenied('This resource belongs to another tenant.')
    return resource


def tenant_control_queryset(company):
    """Return only controls actually applicable to a tenant."""
    from compliance.models import CompanyControl
    return CompanyControl.objects.filter(company=company).select_related(
        'control', 'control__framework', 'control__domain',
    )
