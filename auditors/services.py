"""Phase 4C — deterministic, tenant-safe auditor assignment service."""
from django.utils import timezone

from billing.subscription_access import company_has_active_subscription
from .models import AuditorProfile, AuditorAssignment


def get_auditor_profile(user):
    """Return the user's AuditorProfile or None (never raises)."""
    if not getattr(user, 'is_authenticated', False):
        return None
    return AuditorProfile.objects.filter(user=user).first()


def list_available_auditors():
    """Active + available auditors that a company may assign to."""
    return AuditorProfile.objects.filter(status='active', is_available=True)


def can_company_assign(company):
    """A company may assign a platform auditor only with an active subscription."""
    return company_has_active_subscription(company)


def has_active_assignment(company, auditor):
    return AuditorAssignment.objects.filter(
        company=company, auditor=auditor,
        status__in=AuditorAssignment.ACTIVE_STATUSES).exists()


def create_assignment(company, auditor, requested_by=None, scope='reports_only'):
    """Create an assignment, preventing a duplicate active one. Returns (assignment, created)."""
    if has_active_assignment(company, auditor):
        return AuditorAssignment.objects.filter(
            company=company, auditor=auditor,
            status__in=AuditorAssignment.ACTIVE_STATUSES).first(), False
    a = AuditorAssignment.objects.create(
        company=company, auditor=auditor, requested_by=requested_by, scope=scope)
    return a, True


def assignments_for_user(user):
    """Assignments belonging to the logged-in auditor (auditor.user == user)."""
    profile = get_auditor_profile(user)
    if profile is None:
        return AuditorAssignment.objects.none()
    return AuditorAssignment.objects.filter(auditor=profile).select_related('company')


def get_assignment_for_user(user, assignment_id):
    """Tenant-safe: an assignment only if it belongs to this auditor, else None."""
    profile = get_auditor_profile(user)
    if profile is None:
        return None
    return AuditorAssignment.objects.filter(id=assignment_id, auditor=profile).first()


def auditor_can_view_company_context(assignment):
    """Read-only context is visible only for an ACTIVE auditor with an ACCEPTED assignment."""
    return (assignment is not None
            and assignment.auditor.status == 'active'
            and assignment.status == 'accepted')


def respond_to_assignment(assignment, action):
    """Auditor accepts/rejects a 'requested' assignment. Returns True if changed."""
    if assignment.status != 'requested' or action not in ('accept', 'reject'):
        return False
    assignment.status = 'accepted' if action == 'accept' else 'rejected'
    assignment.responded_at = timezone.now()
    assignment.save(update_fields=['status', 'responded_at', 'updated_at'])
    return True
