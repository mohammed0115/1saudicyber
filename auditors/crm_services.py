"""Phase 8D-3B-ADMIN-CRM-A — Get Solution CRM Console read-only selectors.

Pure read-only selectors for the internal Get Solution operations console. They
NEVER write, never run AI, never change compliance calculations or control
counts, and never issue any certification/accreditation. Every value is derived
from existing data only.
"""
from django.db.models import Count


def companies_overview():
    """All companies with their linked-user count, newest first. Read-only."""
    from core.models import Company
    return (Company.objects.all()
            .annotate(user_count=Count('users', distinct=True))
            .order_by('-created_at'))


def crm_summary():
    """Top-level counts for the CRM dashboard cards. Read-only."""
    from core.models import Company, User
    from .models import AuditorProfile
    return {
        'companies': Company.objects.count(),
        'users': User.objects.count(),
        'auditors_total': AuditorProfile.objects.count(),
        'auditors_pending': AuditorProfile.objects.filter(status='pending_review').count(),
        'auditors_active': AuditorProfile.objects.filter(status='active').count(),
        'unlinked_users': unlinked_users().count(),
    }


def unlinked_users():
    """Authenticated accounts not linked to any company AND not an auditor profile.

    These are exactly the accounts that see "No Company Associated" on compliance
    pages. Platform admins (staff/superuser) are excluded — they intentionally
    have no company. Read-only.
    """
    from core.models import User
    return (User.objects.filter(company__isnull=True, is_staff=False, is_superuser=False)
            .filter(auditor_profile__isnull=True)
            .order_by('-date_joined'))


def company_operational_snapshot(company):
    """A compact, read-only operational snapshot for one company.

    Returns booleans/strings describing where the company is in the journey. All
    lookups are existence checks against existing data; nothing is computed,
    written, or scored here.
    """
    snap = {
        'linked_users': [],
        'approved_frameworks': [],
        'has_classification': False,
        'has_applicability': False,
        'has_evidence': False,
        'has_auditor_assignment': False,
        'has_auditor_verdict': False,
        'has_reviewed_report': False,
    }
    # Linked users (always available from core).
    snap['linked_users'] = list(company.users.all().order_by('email'))

    # Compliance signals — imported lazily and guarded so the console never 500s
    # if an optional table/relationship is unavailable in some environment.
    try:
        from compliance.models import (CompanyIntakeProfile, FrameworkApplicabilityResult,
                                        CompanyFrameworkScope, EvidenceSubmission,
                                        AuditorFinalVerdict)
        snap['has_classification'] = bool(
            getattr(company, 'classification_date', None)
            or CompanyIntakeProfile.objects.filter(company=company).exists())
        snap['has_applicability'] = FrameworkApplicabilityResult.objects.filter(company=company).exists()
        snap['approved_frameworks'] = list(
            CompanyFrameworkScope.objects.filter(company=company, status='approved')
            .select_related('framework_version', 'framework_version__framework')
            .values_list('framework_version__code', flat=True))
        snap['has_evidence'] = EvidenceSubmission.objects.filter(company=company).exists()
        snap['has_auditor_verdict'] = AuditorFinalVerdict.objects.filter(
            submission__company=company).exists()
        snap['has_reviewed_report'] = snap['has_auditor_verdict']
    except Exception:
        pass

    try:
        from .models import AuditorAssignment
        snap['has_auditor_assignment'] = AuditorAssignment.objects.filter(
            company=company, status__in=['requested', 'accepted', 'completed']).exists()
    except Exception:
        pass

    return snap
