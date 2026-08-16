"""Transactional services for company tenancy and journey state."""
from __future__ import annotations

from django.db import transaction

from core.models import CompanyJourney, CompanyMembership


@transaction.atomic
def ensure_company_membership(user, company, *, role=None, make_default=True):
    """Create or reactivate a tenant membership and retain legacy compatibility."""
    membership, _ = CompanyMembership.objects.select_for_update().get_or_create(
        user=user,
        company=company,
        defaults={
            'role': role or getattr(user, 'role', 'compliance_officer'),
            'is_active': True,
            # Set the default after releasing any previous default below; doing
            # it during INSERT would violate the partial unique constraint.
            'is_default': False,
        },
    )
    changed = False
    if role and membership.role != role:
        membership.role = role
        changed = True
    if not membership.is_active:
        membership.is_active = True
        membership.revoked_at = None
        changed = True
    if make_default:
        CompanyMembership.objects.filter(user=user, is_default=True).exclude(pk=membership.pk).update(is_default=False)
        if not membership.is_default:
            membership.is_default = True
            changed = True
    if changed:
        membership.save()

    # Old views keep using user.company while progressive migration moves them
    # to core.tenancy.active_company_for(). Keep that pointer synchronized.
    if getattr(user, 'company_id', None) != company.id:
        user.company = company
        user.save(update_fields=['company'])
    return membership


@transaction.atomic
def ensure_company_journey(company, *, state='registered', reason=''):
    """Create the single journey record; never overwrite a later existing state."""
    journey, created = CompanyJourney.objects.select_for_update().get_or_create(
        company=company,
        defaults={'state': state, 'state_reason': reason[:250]},
    )
    return journey, created


@transaction.atomic
def transition_company_journey(company, state, *, reason=''):
    """Persist a deliberate, versioned company journey transition."""
    journey, _ = ensure_company_journey(company)
    if journey.state != state:
        journey.state = state
        journey.state_reason = reason[:250]
        journey.version += 1
        journey.save(update_fields=['state', 'state_reason', 'version', 'updated_at'])
    return journey
