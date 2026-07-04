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


# ============================================================
# Phase 8D-3D-CRM-B — Company/User linking actions (write, staff-only).
# Business rules live here (service layer). Every action is audited via the
# existing core.AuditLog (no new model / no migration). Never creates users or
# companies, never changes the current session, never touches compliance data.
# ============================================================
class CRMLinkError(Exception):
    """Raised for an invalid link/unlink request (permission / eligibility)."""


def is_platform_admin(user):
    """Reuse the canonical Get Solution staff/superuser check."""
    from .admin_services import is_platform_admin as _p
    return _p(user)


def user_is_linkable(user):
    """True if a user account is eligible to be linked as a company user.

    Eligible = a normal account: not staff/superuser, no auditor profile, and not
    already linked to a company. (Cross-role accounts are never linked as company
    users to avoid role/session confusion.)
    """
    if user is None:
        return False
    if user.is_staff or user.is_superuser:
        return False
    from .services import get_auditor_profile
    if get_auditor_profile(user) is not None:
        return False
    return getattr(user, 'company_id', None) is None


def linkable_users():
    """Unlinked accounts eligible to be linked to a company (same set as the
    'unlinked accounts' the customer would see 'No Company Associated')."""
    return unlinked_users()


def _crm_audit(actor, action, company, extra=None):
    """Durably record a CRM action in core.AuditLog (no migration). Every CRM audit
    carries `company_id` so the per-company activity timeline can find it."""
    try:
        from core.models import AuditLog
        meta = {
            'company_id': getattr(company, 'id', None),
            'company_name': getattr(company, 'name', '') if company else '',
            'performed_by': getattr(actor, 'email', ''),
        }
        if extra:
            meta.update(extra)
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=f'crm_{action}'[:100],
            path='/platform-admin/companies/',
            metadata=meta,
        )
    except Exception:
        # Auditing must never block the operational action.
        pass


def _record_link_audit(actor, action, target_user, old_company, new_company, reason):
    """Record a link/unlink action. `company_id` = the affected company so it shows
    up on that company's activity timeline."""
    company = new_company or old_company
    _crm_audit(actor, action, company, {
        'target_user_id': getattr(target_user, 'id', None),
        'target_user_email': getattr(target_user, 'email', ''),
        'old_company_id': getattr(old_company, 'id', None),
        'old_company_name': getattr(old_company, 'name', '') if old_company else '',
        'new_company_id': getattr(new_company, 'id', None),
        'new_company_name': getattr(new_company, 'name', '') if new_company else '',
        'reason': (reason or '')[:1000],
    })


def link_user_to_company(actor, user, company, reason):
    """Link an existing normal user account to an existing company. Staff-only.

    Raises CRMLinkError on permission / missing data / eligibility / already-linked.
    Never creates users/companies; never changes the acting admin's session.
    """
    if not is_platform_admin(actor):
        raise CRMLinkError('ليست لديك صلاحية تنفيذ هذا الإجراء.')
    if not (reason or '').strip():
        raise CRMLinkError('السبب مطلوب لتنفيذ الربط.')
    if user is None:
        raise CRMLinkError('الحساب المستهدف غير موجود.')
    if company is None:
        raise CRMLinkError('الشركة المستهدفة غير موجودة.')
    if user.is_staff or user.is_superuser:
        raise CRMLinkError('لا يمكن ربط حساب موظّف/مسؤول كحساب شركة.')
    from .services import get_auditor_profile
    if get_auditor_profile(user) is not None:
        raise CRMLinkError('لا يمكن ربط حساب مدقّق كحساب شركة.')
    if getattr(user, 'company_id', None) is not None:
        # Fail closed: this phase does not implement "move user".
        raise CRMLinkError('الحساب مرتبط بشركة أخرى بالفعل. إلغاء الربط الحالي أولًا.')

    user.company = company
    if not user.role or user.role in ('', 'admin'):
        user.role = 'company_admin'
    user.save(update_fields=['company', 'role'])
    _record_link_audit(actor, 'link_user', user, None, company, reason)
    return user


def unlink_user_from_company(actor, user, reason):
    """Clear a normal user's company link. Staff-only. Never deletes anything.

    Raises CRMLinkError on permission / missing data / ineligible target.
    """
    if not is_platform_admin(actor):
        raise CRMLinkError('ليست لديك صلاحية تنفيذ هذا الإجراء.')
    if not (reason or '').strip():
        raise CRMLinkError('السبب مطلوب لتنفيذ إلغاء الربط.')
    if user is None:
        raise CRMLinkError('الحساب المستهدف غير موجود.')
    if user.is_staff or user.is_superuser:
        raise CRMLinkError('لا يمكن تعديل ربط حساب موظّف/مسؤول من هنا.')
    from .services import get_auditor_profile
    if get_auditor_profile(user) is not None:
        raise CRMLinkError('هذا حساب مدقّق ولا يُدار من هنا.')
    old_company = getattr(user, 'company', None)
    if old_company is None:
        raise CRMLinkError('الحساب غير مرتبط بأي شركة.')

    user.company = None
    user.save(update_fields=['company'])
    _record_link_audit(actor, 'unlink_user', user, old_company, None, reason)
    return user


# ============================================================
# Phase 8D-3E-CRM-C — internal CRM notes / status / activity timeline.
# Staff-only writes; every change is audited. Never affects compliance, control
# counts, login, subscription, or access. Notes are internal-only.
# ============================================================
VALID_CRM_STATUSES = {'new', 'onboarding', 'active', 'needs_follow_up', 'blocked', 'inactive'}


def get_company_crm_profile(company):
    """Return the company's CRM profile or None (read-only; never creates)."""
    from .models import CompanyCRMProfile
    return CompanyCRMProfile.objects.filter(company=company).select_related(
        'assigned_staff', 'updated_by').first()


def assignable_staff():
    """Get Solution staff/superuser accounts eligible to be a company's assignee."""
    from core.models import User
    from django.db.models import Q
    return User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by('email')


def company_subscription_summary(company):
    """Phase 8I — staff-only subscription summary for a company (read-only, no card data)."""
    summary = {'plan': '', 'status': 'inactive', 'starts_at': None, 'ends_at': None,
               'trial_ends_at': None, 'pending_payments': 0, 'last_payment_status': '—',
               'subscription_id': None, 'last_payment_provider': '—', 'last_payment_reference': '',
               'last_payment_provider_id': '', 'pending_moyasar_payments': 0,
               'failed_moyasar_payments': 0, 'last_payment_paid_at': None,
               'last_moyasar_status': ''}
    try:
        from billing.subscription_access import get_company_subscription
        from billing.models import Payment
        sub = get_company_subscription(company)
        if sub is not None:
            summary.update({
                'plan': (sub.plan.name if sub.plan_id else sub.plan_name) or '—',
                'status': sub.status, 'status_display': sub.get_status_display(),
                'starts_at': sub.starts_at, 'ends_at': sub.ends_at,
                'trial_ends_at': sub.trial_ends_at, 'subscription_id': sub.id,
            })
        summary['pending_payments'] = Payment.objects.filter(company=company, status='pending').count()
        summary['pending_moyasar_payments'] = Payment.objects.filter(
            company=company, status='pending', provider='moyasar').count()
        summary['failed_moyasar_payments'] = Payment.objects.filter(
            company=company, provider='moyasar', status__in=('failed', 'cancelled')).count()
        last = Payment.objects.filter(company=company).order_by('-created_at').first()
        if last is not None:
            # Read-only, no card data / no secrets / no raw payload: safe fields only.
            summary['last_payment_status'] = last.get_status_display()
            summary['last_payment_provider'] = last.get_provider_display()
            summary['last_payment_reference'] = last.reference or ''
            summary['last_payment_provider_id'] = last.provider_payment_id or ''
            summary['last_payment_paid_at'] = last.paid_at
            summary['last_moyasar_status'] = (last.provider_metadata or {}).get('last_provider_status', '')
    except Exception:
        pass
    return summary


def company_report_summary(company):
    """Phase 8H — staff-only internal readiness-report summary (read-only, counts only)."""
    summary = {'readiness_percent': 0, 'missing': 0, 'open_risks': 0,
               'overdue_tasks': 0, 'report_date': None}
    try:
        from compliance.gap_engine import get_company_gap_summary
        from risk import services as risk_services
        from core.models import AuditLog
        g = get_company_gap_summary(company)
        counts = risk_services.risk_dashboard_counts(company)
        summary.update({
            'readiness_percent': g.get('overall_readiness_percent', 0),
            'missing': g.get('missing_count', 0),
            'open_risks': counts['open'],
            'overdue_tasks': counts['overdue_tasks'],
        })
        log = (AuditLog.objects.filter(action__in=['report_viewed', 'report_refreshed'])
               .filter(metadata__company_id=company.id).order_by('-created_at').first())
        if log is not None:
            summary['report_date'] = log.created_at
    except Exception:
        pass
    return summary


def company_risk_summary(company):
    """Phase 8G — staff-only internal risk summary for a company (read-only, counts only)."""
    summary = {'open': 0, 'high_critical': 0, 'overdue_tasks': 0, 'total': 0, 'last_generated': None}
    try:
        from risk import services as risk_services
        from core.models import AuditLog
        counts = risk_services.risk_dashboard_counts(company)
        summary.update({'open': counts['open'], 'high_critical': counts['high_critical'],
                        'overdue_tasks': counts['overdue_tasks'], 'total': counts['total']})
        log = (AuditLog.objects.filter(action='risk_generated_from_gap')
               .filter(metadata__company_id=company.id).order_by('-created_at').first())
        if log is not None:
            summary['last_generated'] = log.created_at
    except Exception:
        pass
    return summary


def company_gap_summary(company):
    """Phase 8F — staff-only preliminary gap-readiness summary for a company.

    Read-only aggregate over the company's stored ControlGapAssessment rows; never
    exposes control-level evidence content. Guarded so it never 500s.
    """
    summary = {'readiness_percent': 0, 'missing': 0, 'needs_review': 0,
               'total': 0, 'calculated_at': None}
    try:
        from compliance.gap_engine import get_company_gap_summary
        s = get_company_gap_summary(company)
        summary.update({
            'readiness_percent': s.get('overall_readiness_percent', 0),
            'missing': s.get('missing_count', 0),
            'needs_review': s.get('needs_review_count', 0),
            'total': s.get('total', 0),
            'calculated_at': s.get('calculated_at'),
        })
    except Exception:
        pass
    return summary


def company_evidence_summary(company):
    """Phase 8E — staff-only evidence counts for a company (read-only, no content).

    Returns {uploaded, extracted, manual_review, failed}. Never exposes evidence
    text/files to the CRM — counts only. Guarded so it never 500s.
    """
    summary = {'uploaded': 0, 'extracted': 0, 'manual_review': 0, 'failed': 0}
    try:
        from compliance.models import EvidenceSubmission, EvidenceTextExtraction
        summary['uploaded'] = EvidenceSubmission.objects.filter(company=company).count()
        ext = EvidenceTextExtraction.objects.filter(submission__company=company)
        summary['extracted'] = ext.filter(status='extracted', char_count__gt=0).count()
        summary['failed'] = ext.filter(status='failed').count()
        summary['manual_review'] = ext.filter(
            status__in=['no_text_extracted', 'unsupported_type', 'too_large']).count()
    except Exception:
        pass
    return summary


def company_notes(company):
    """Internal CRM notes for a company, newest first (read-only)."""
    from .models import CompanyCRMNote
    return CompanyCRMNote.objects.filter(company=company).select_related('author')


def add_company_note(actor, company, text):
    """Create an internal CRM note on a company. Staff-only; text required."""
    from .models import CompanyCRMNote
    if not is_platform_admin(actor):
        raise CRMLinkError('ليست لديك صلاحية إضافة ملاحظات CRM.')
    text = (text or '').strip()
    if not text:
        raise CRMLinkError('نص الملاحظة مطلوب.')
    if company is None:
        raise CRMLinkError('الشركة غير موجودة.')
    note = CompanyCRMNote.objects.create(
        company=company, author=actor if getattr(actor, 'is_authenticated', False) else None,
        text=text[:5000], visibility='internal')
    _crm_audit(actor, 'note_added', company, {
        'note_id': note.id, 'note_excerpt': text[:200]})
    return note


def update_company_crm_status(actor, company, *, crm_status=None, assigned_staff_id=None,
                              next_follow_up_date=None, internal_summary=None, reason=''):
    """Create/update the company's CRM follow-up profile. Staff-only.

    Never touches compliance/subscription/access. Records old -> new in AuditLog.
    """
    from .models import CompanyCRMProfile
    from core.models import User
    if not is_platform_admin(actor):
        raise CRMLinkError('ليست لديك صلاحية تحديث حالة CRM.')
    if company is None:
        raise CRMLinkError('الشركة غير موجودة.')
    if crm_status is not None and crm_status not in VALID_CRM_STATUSES:
        raise CRMLinkError('حالة CRM غير صالحة.')

    profile, _created = CompanyCRMProfile.objects.get_or_create(company=company)
    old_status = profile.crm_status

    if crm_status is not None:
        profile.crm_status = crm_status
    if assigned_staff_id is not None:
        try:
            sid = int(assigned_staff_id)
        except (TypeError, ValueError):
            sid = 0
        if sid <= 0:
            profile.assigned_staff = None
        else:
            staff = User.objects.filter(id=sid).first()
            # Only a Get Solution staff/superuser account may be an assignee.
            if staff is not None and (staff.is_staff or staff.is_superuser):
                profile.assigned_staff = staff
    if next_follow_up_date is not None:
        if isinstance(next_follow_up_date, str):
            from django.utils.dateparse import parse_date
            next_follow_up_date = parse_date(next_follow_up_date) if next_follow_up_date else None
        profile.next_follow_up_date = next_follow_up_date or None
    if internal_summary is not None:
        profile.internal_summary = (internal_summary or '')[:5000]
    profile.updated_by = actor if getattr(actor, 'is_authenticated', False) else None
    profile.save()

    _crm_audit(actor, 'status_changed', company, {
        'old_status': old_status,
        'new_status': profile.crm_status,
        'assigned_staff_id': profile.assigned_staff_id,
        'next_follow_up_date': profile.next_follow_up_date.isoformat() if profile.next_follow_up_date else None,
        'reason': (reason or '')[:1000],
    })
    return profile


# Human-friendly labels for the activity timeline.
CRM_ACTIVITY_LABELS = {
    'crm_link_user': 'ربط مستخدم بالشركة · User linked',
    'crm_unlink_user': 'إلغاء ربط مستخدم · User unlinked',
    'crm_note_added': 'إضافة ملاحظة داخلية · Internal note added',
    'crm_status_changed': 'تغيير حالة المتابعة · Follow-up status changed',
    'auditor_approve': 'اعتماد مدقق · Auditor approved',
    'auditor_reject': 'رفض مدقق · Auditor rejected',
    'auditor_suspend': 'إيقاف مدقق · Auditor suspended',
    'auditor_reactivate': 'إعادة تفعيل مدقق · Auditor reactivated',
}


def get_company_activity_timeline(company, limit=25):
    """Recent internal CRM events for a company, newest first (read-only).

    Reuses core.AuditLog (no duplicate audit system). Filtered in Python by the
    `company_id` stored in each CRM audit's metadata, so it is DB-agnostic and
    never 500s when there is no activity yet.
    """
    from core.models import AuditLog
    recent = (AuditLog.objects.filter(action__startswith='crm_')
              .select_related('user').order_by('-created_at')[:500])
    events = []
    for log in recent:
        meta = log.metadata or {}
        if meta.get('company_id') != company.id:
            continue
        events.append({
            'action': log.action,
            'label': CRM_ACTIVITY_LABELS.get(log.action, log.action),
            'actor': meta.get('performed_by') or (log.user.email if log.user else ''),
            'created_at': log.created_at,
            'detail': _activity_detail(log.action, meta),
        })
        if len(events) >= limit:
            break
    return events


def _activity_detail(action, meta):
    if action == 'crm_link_user':
        return meta.get('target_user_email', '')
    if action == 'crm_unlink_user':
        return meta.get('target_user_email', '')
    if action == 'crm_note_added':
        return meta.get('note_excerpt', '')
    if action == 'crm_status_changed':
        return '%s → %s' % (meta.get('old_status', ''), meta.get('new_status', ''))
    return ''


def platform_data_health():
    """PILOT-HOTFIX-B (B) — official-data health for the platform-admin console.

    Staff-only, read-only counts (no secrets). Flags when the official control dataset
    is missing or only a small pilot subset is loaded.
    """
    from compliance.models import Framework, FrameworkVersion, Control
    EXPECTED_CONTROLS = 417
    health = {'framework_count': 0, 'framework_version_count': 0, 'control_count': 0,
              'expected_controls': EXPECTED_CONTROLS, 'status': 'ok', 'message': ''}
    try:
        health['framework_count'] = Framework.objects.count()
        health['framework_version_count'] = FrameworkVersion.objects.count()
        controls = Control.objects.filter(is_legacy_import=False).count()
        health['control_count'] = controls
        if controls == 0:
            health['status'] = 'empty'
            health['message'] = ('لا توجد ضوابط رسمية محمّلة · No official controls loaded — '
                                 'the compliance dataset is not installed.')
        elif controls < EXPECTED_CONTROLS:
            health['status'] = 'pilot'
            health['message'] = ('ضوابط تجريبية محمّلة · Pilot controls loaded — the full '
                                 'official dataset (%d) is not loaded yet.' % EXPECTED_CONTROLS)
        else:
            health['status'] = 'ok'
            health['message'] = 'مجموعة الضوابط الرسمية محمّلة · Official control dataset loaded.'
    except Exception:
        health['status'] = 'unknown'
    return health
