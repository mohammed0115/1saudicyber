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
    from .models import AuditorProfile, AuditorAssignment
    data = {
        'companies': Company.objects.count(),
        'users': User.objects.count(),
        'auditors_total': AuditorProfile.objects.count(),
        'auditors_pending': AuditorProfile.objects.filter(status='pending_review').count(),
        'auditors_active': AuditorProfile.objects.filter(status='active').count(),
        'unlinked_users': unlinked_users().count(),
        'active_assignments': AuditorAssignment.objects.filter(status='accepted').count(),
    }
    # Operational KPIs — each guarded so a missing/renamed model never breaks the dashboard.
    try:
        from compliance.models import Assessment, CompanyFrameworkScope
        data['assessments_under_review'] = Assessment.objects.filter(status='auditor_review').count()
        data['pending_scope_approvals'] = CompanyFrameworkScope.objects.filter(status='pending').count()
    except Exception:
        data.setdefault('assessments_under_review', 0)
        data.setdefault('pending_scope_approvals', 0)
    try:
        from billing.models import CompanySubscription
        data['active_subscriptions'] = CompanySubscription.objects.filter(status='active').count()
    except Exception:
        data['active_subscriptions'] = 0
    try:
        from auditor_portal.models import DocumentRequest
        data['open_rfis'] = DocumentRequest.objects.filter(status__in=DocumentRequest.OPEN_STATES).count()
    except Exception:
        data['open_rfis'] = 0
    return data


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


def company_framework_entitlement(company):
    """UAT-...-F1: read-only truth about approved-framework usage vs the plan's
    `max_frameworks`.

    IMPORTANT (source-verified): `max_frameworks` is a DISPLAY-ONLY plan characteristic.
    It is NOT in `billing.access.FEATURE_LIMIT`, and no approval path (approve_company_scope
    / approve_framework_scope) checks it — framework approval is applicability-driven and
    happens BEFORE a subscription exists. So the plan limit is not currently enforced.

    `enforced` is derived from the real FEATURE_LIMIT map (not hard-coded), so this helper
    self-corrects the moment framework enforcement is ever added. Never mutates data.
    """
    info = {'approved_count': 0, 'plan_limit': 0, 'enforced': False,
            'at_limit': False, 'over_limit': False, 'remaining': None, 'can_add_framework': True}
    if company is None:
        return info
    try:
        from compliance.models import CompanyFrameworkScope
        info['approved_count'] = CompanyFrameworkScope.objects.filter(
            company=company, status='approved').count()
    except Exception:
        pass
    try:
        from billing.subscription_services import subscription_limit_value
        from billing.access import FEATURE_LIMIT
        info['plan_limit'] = subscription_limit_value(company, 'max_frameworks')
        info['enforced'] = 'max_frameworks' in FEATURE_LIMIT.values()
    except Exception:
        pass
    limit = info['plan_limit']
    if info['enforced'] and limit and limit > 0:
        info['remaining'] = max(0, limit - info['approved_count'])
        info['at_limit'] = info['approved_count'] == limit
        info['over_limit'] = info['approved_count'] > limit
        info['can_add_framework'] = info['approved_count'] < limit
    else:
        # Not enforced (or no positive limit): this limit never blocks additions.
        info['can_add_framework'] = True
    return info


def auditor_review_state(company):
    """UAT-...-F4: centralized, persisted auditor-review milestones for CRM/admin
    journey consumption. Three DISTINCT milestones derived only from real workflow
    data (never from a mere auditor assignment/request):

      - review_started      : the auditor did meaningful review work.
      - has_final_verdict    : a final auditor verdict exists.
      - has_final_report     : a qualifying final (submitted) review report exists.

    Monotonic by construction: has_final_report -> has_final_verdict -> review_started.
    Backward compatible with the legacy compliance signals (AuditorFinalVerdict /
    ControlAssessment) — they still count as review activity / a final verdict.
    """
    state = {'review_started': False, 'has_final_verdict': False, 'has_final_report': False}
    if company is None:
        return state

    # auditor_portal — the workflow the auditor actually uses (Phase A/B/C).
    has_report = has_control_verdict = has_note = False
    try:
        from auditor_portal.models import AuditReport, AuditorControlVerdict, AuditorNote
        has_report = AuditReport.objects.filter(assessment__company=company).exists()
        has_control_verdict = AuditorControlVerdict.objects.filter(
            assessment__company=company,
            status__in=AuditorControlVerdict.REVIEWED_STATES).exists()
        has_note = AuditorNote.objects.filter(assessment__company=company).exists()
    except Exception:
        pass

    # Legacy compliance signals (per-submission final verdict / per-control assessment).
    has_final_verdict_row = has_control_assessment = False
    try:
        from compliance.models import AuditorFinalVerdict, ControlAssessment
        has_final_verdict_row = AuditorFinalVerdict.objects.filter(
            submission__company=company).exists()
        has_control_assessment = (ControlAssessment.objects.filter(company=company)
                                  .exclude(status='not_reviewed').exists())
    except Exception:
        pass

    # Step 12 — a qualifying FINAL report. AuditReport is created only by submit_report
    # (a deliberate final action; there is no draft AuditReport), so its existence == final.
    state['has_final_report'] = has_report
    # Step 11 — a FINAL VERDICT exists: the named final-verdict model, OR a submitted
    # report (which carries an overall pass/conditional/fail final verdict).
    state['has_final_verdict'] = has_final_verdict_row or has_report
    # Step 10 — MEANINGFUL review work: any real review artifact (control verdict, note,
    # final verdict, control assessment, or report). NOT satisfied by assignment/request.
    state['review_started'] = (has_control_verdict or has_note or has_final_verdict_row
                               or has_control_assessment or has_report)
    return state


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
        # F4: consume the centralized auditor-review state so the operational-status
        # display and the admin journey agree. has_auditor_verdict == a final verdict;
        # has_reviewed_report == a qualifying final report (no longer the same signal).
        _review = auditor_review_state(company)
        snap['has_auditor_verdict'] = _review['has_final_verdict']
        snap['has_reviewed_report'] = _review['has_final_report']
    except Exception:
        pass

    try:
        from .models import AuditorAssignment
        snap['has_auditor_assignment'] = AuditorAssignment.objects.filter(
            company=company, status__in=['requested', 'accepted', 'completed']).exists()
    except Exception:
        pass

    return snap


def company_journey_summary(company):
    """Read-only compliance-journey summary for the Get Solution CRM console (INTERNAL ONLY).

    Existence checks + the advisory classification engine — nothing is written or scored here.
    Never exposed to company users or auditors. Guarded so the console never 500s.
    """
    summary = {
        'classification_done': False,
        'proposed_frameworks': 0,
        'approved_frameworks': 0,
        'expected_controls': 0,
        'generated_controls': 0,
        'risk_level': '',
        'risk_level_ar': '—',
        'scope_approved': False,
        'control_plan_generated': False,
        'email_verified': False,
        'last_activity': getattr(company, 'updated_at', None),
    }
    try:
        from compliance.models import (CompanyIntakeProfile, CompanyFrameworkScope,
                                        ControlApplicabilityResult)
        has_intake = CompanyIntakeProfile.objects.filter(company=company).exists()
        summary['classification_done'] = has_intake
        scopes = CompanyFrameworkScope.objects.filter(company=company)
        summary['scope_approved'] = scopes.filter(status='approved').exists()
        summary['approved_frameworks'] = scopes.filter(status='approved').count()
        # Controls ACTUALLY generated into the plan (distinct from the advisory expected count).
        gen = ControlApplicabilityResult.objects.filter(company=company, decision='applicable')
        summary['generated_controls'] = gen.count()
        summary['control_plan_generated'] = gen.exists()
        if has_intake:
            # Same advisory engine the company sees — keeps CRM and company views consistent.
            from compliance.smart_classification import classify_company
            r = classify_company(company)
            summary['proposed_frameworks'] = r.recommended_count
            summary['expected_controls'] = r.total_expected_controls
            summary['risk_level'] = r.risk_level
            summary['risk_level_ar'] = r.risk_level_ar
        else:
            # No intake yet: fall back to any non-rejected proposed scope rows.
            summary['proposed_frameworks'] = scopes.exclude(status='rejected').count()
    except Exception:
        pass
    try:
        summary['email_verified'] = company.users.filter(email_verified=True).exists()
    except Exception:
        pass
    try:
        from core.models import AuditLog
        last = AuditLog.objects.filter(company=company).order_by('-created_at').first()
        if last is not None:
            summary['last_activity'] = last.created_at
    except Exception:
        pass
    # Proposed framework codes (for a compact read-only inline list) + the 8-step journey.
    summary['proposed_framework_codes'] = []
    summary['steps'] = []
    summary['current_step_label'] = ''
    summary['next_action_text'] = ''
    try:
        from compliance.models import (CompanyFrameworkScope, EvidenceSubmission, ControlAssessment)
        summary['proposed_framework_codes'] = list(
            CompanyFrameworkScope.objects.filter(company=company)
            .exclude(status='rejected')
            .values_list('framework_version__code', flat=True))
        has_intake = summary['classification_done']
        evidence_done = EvidenceSubmission.objects.filter(company=company).exists()
        # F4: the "auditor reviewed" milestone consumes the centralized review state
        # (a superset of the legacy ControlAssessment signal — no company loses it),
        # so the 8-step and 12-step journeys agree on when auditor review has happened.
        auditor_done = auditor_review_state(company)['review_started']
        reports_done = auditor_done  # reports become meaningful after auditor review exists
        step_defs = [
            ('registration', 'إنشاء حساب الشركة', True),
            ('classification', 'ملف التصنيف', has_intake),
            ('framework_review', 'مراجعة الأطر', has_intake and summary['proposed_frameworks'] > 0),
            ('scope_approval', 'اعتماد نطاق الأطر', summary['scope_approved']),
            ('control_plan', 'خطة الضوابط', summary['control_plan_generated']),
            ('evidence', 'رفع الأدلة', evidence_done),
            ('auditor_review', 'مراجعة المدقق', auditor_done),
            ('reports', 'التقارير', reports_done),
        ]
        # First not-completed step is "current"; everything after it is "locked".
        current_assigned = False
        steps = []
        for key, label, done in step_defs:
            if done:
                status = 'completed'
            elif not current_assigned:
                status = 'current'
                current_assigned = True
            else:
                status = 'locked'
            steps.append({'key': key, 'label': label, 'status': status})
        summary['steps'] = steps
        _WAITING = {
            'classification': 'بانتظار إكمال ملف التصنيف',
            'framework_review': 'بانتظار إكمال التصنيف لتحديد الأطر',
            'scope_approval': 'بانتظار اعتماد نطاق الأطر',
            'control_plan': 'بانتظار إنشاء خطة الضوابط',
            'evidence': 'بانتظار رفع الأدلة',
            'auditor_review': 'بانتظار مراجعة المدقق',
            'reports': 'بانتظار توفّر التقارير',
        }
        _NEXT = {
            'classification': 'الشركة تحتاج إكمال ملف التصنيف.',
            'framework_review': 'الشركة تحتاج إكمال التصنيف لتحديد الأطر المقترحة.',
            'scope_approval': 'الشركة تحتاج اعتماد نطاق الأطر قبل إنشاء خطة الضوابط.',
            'control_plan': 'بانتظار إنشاء خطة الضوابط بعد اعتماد النطاق.',
            'evidence': 'بانتظار رفع الأدلة المطلوبة من الشركة.',
            'auditor_review': 'بانتظار مراجعة المدقق للأدلة.',
            'reports': 'بانتظار توفّر التقارير بعد مراجعة المدقق.',
        }
        cur = next((s for s in steps if s['status'] == 'current'), None)
        if cur is not None:
            summary['current_step_label'] = _WAITING.get(cur['key'], cur['label'])
            summary['next_action_text'] = _NEXT.get(cur['key'], '')
        else:
            summary['current_step_label'] = 'اكتملت الرحلة'
            summary['next_action_text'] = 'اكتملت مراحل الرحلة الحالية.'
    except Exception:
        pass
    return summary


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
    # Safety: never strand a company without an admin. If this is the ONLY active company admin,
    # block the unlink — the operator must link another admin first (safe fallback).
    if user.role == 'company_admin':
        other_admins = (old_company.users.filter(role='company_admin', is_active=True)
                        .exclude(id=user.id))
        if not other_admins.exists():
            raise CRMLinkError('لا يمكن إلغاء ربط آخر مسؤول للشركة. اربط مسؤولًا آخر أولًا '
                               'لتفادي فقدان الشركة الوصول إلى حسابها.')

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
               'overdue_tasks': 0, 'report_date': None, 'readiness_available': False}
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
            # F2: readiness exists iff there are stored gap rows (not from percent == 0).
            'readiness_available': g.get('total', 0) > 0,
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
               'total': 0, 'calculated_at': None, 'readiness_available': False}
    try:
        from compliance.gap_engine import get_company_gap_summary
        s = get_company_gap_summary(company)
        total = s.get('total', 0)
        summary.update({
            'readiness_percent': s.get('overall_readiness_percent', 0),
            'missing': s.get('missing_count', 0),
            'needs_review': s.get('needs_review_count', 0),
            'total': total,
            'calculated_at': s.get('calculated_at'),
            # F2: a readiness calculation exists iff there are stored gap rows —
            # NOT inferred from readiness_percent == 0.
            'readiness_available': total > 0,
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
        # F3: 'manual_review' here means the auto text-EXTRACTION produced no usable text
        # (image/unsupported/too large) so the file must be read by a human. It is NOT an
        # auditor/compliance review. Key kept for compatibility; UI labels say
        # "تحتاج قراءة يدوية (استخراج)".
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
    'crm_link_user': 'ربط مستخدم بالشركة',
    'crm_unlink_user': 'إلغاء ربط مستخدم',
    'crm_note_added': 'إضافة ملاحظة داخلية',
    'crm_status_changed': 'تغيير حالة المتابعة',
    'auditor_approve': 'اعتماد مدقق',
    'auditor_reject': 'رفض مدقق',
    'auditor_suspend': 'إيقاف مدقق',
    'auditor_reactivate': 'إعادة تفعيل مدقق',
    # UAT-PLATFORM-ADMIN-JOURNEY — admin-initiated auditor engagement (Arabic-only).
    'crm_admin_auditor_assigned': 'إسناد مدقق من الإدارة',
    'crm_admin_auditor_request_cancelled': 'إلغاء طلب مدقق من الإدارة',
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


# Arabic labels for CRM follow-up statuses (for readable activity messages).
CRM_STATUS_AR = {
    'new': 'جديدة', 'onboarding': 'تهيئة', 'active': 'نشطة',
    'needs_follow_up': 'تحتاج متابعة', 'blocked': 'محظورة', 'inactive': 'غير نشطة',
}


def _activity_detail(action, meta):
    if action == 'crm_link_user':
        return meta.get('target_user_email', '')
    if action == 'crm_unlink_user':
        return meta.get('target_user_email', '')
    if action == 'crm_note_added':
        return meta.get('note_excerpt', '')
    if action == 'crm_status_changed':
        old = CRM_STATUS_AR.get(meta.get('old_status', ''), meta.get('old_status', ''))
        new = CRM_STATUS_AR.get(meta.get('new_status', ''), meta.get('new_status', ''))
        return 'من «%s» إلى «%s»' % (old, new)
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
            health['message'] = 'لا توجد ضوابط رسمية محمّلة — مجموعة بيانات الامتثال غير مثبّتة.'
        elif controls < EXPECTED_CONTROLS:
            health['status'] = 'pilot'
            health['message'] = ('ضوابط تجريبية محمّلة — لم تُحمّل بعد المجموعة الرسمية '
                                 'الكاملة (%d).' % EXPECTED_CONTROLS)
        else:
            health['status'] = 'ok'
            health['message'] = 'مجموعة الضوابط الرسمية محمّلة.'
    except Exception:
        health['status'] = 'unknown'
    return health


# ============================================================
# UAT-PLATFORM-ADMIN-JOURNEY-COMPLETE-UX-LOGIC-A
# Internal admin operational journey + auditor-engagement view. Read-only,
# staff-only (rendered on the platform-admin company page). Reuses the SAME
# signals as company_journey_summary/company_operational_snapshot — no new
# scoring, no compliance-logic changes, no model changes.
# ============================================================
_ENGAGEMENT_STATUS_AR = {
    'none': 'لا يوجد', 'requested': 'بانتظار موافقة المدقق',
    'accepted': 'مقبول / مُسند', 'rejected': 'مرفوض', 'cancelled': 'ملغى',
    'completed': 'مكتمل',
}


def admin_auditor_engagement(company):
    """The company's auditor engagement as the admin sees it (read-only + action flags)."""
    from .models import AuditorAssignment
    active = (AuditorAssignment.objects
              .filter(company=company, status__in=AuditorAssignment.ACTIVE_STATUSES)
              .select_related('auditor', 'auditor__user', 'requested_by').first())
    latest = (AuditorAssignment.objects.filter(company=company)
              .select_related('auditor', 'auditor__user', 'requested_by')
              .order_by('-requested_at').first())
    last_rejected = (AuditorAssignment.objects.filter(company=company, status='rejected')
                     .select_related('auditor').order_by('-responded_at').first())

    def _source(a):
        if a is None or a.requested_by is None:
            return 'company'
        by = a.requested_by
        return 'admin' if (getattr(by, 'is_staff', False) or getattr(by, 'is_superuser', False)) else 'company'

    ref = active or latest
    status = active.status if active else (latest.status if latest else 'none')
    src = _source(ref)
    return {
        'active': active,
        'latest': latest,
        'last_rejected': last_rejected,
        'assignment': ref,
        'auditor': ref.auditor if ref else None,
        'status': status,
        'status_ar': _ENGAGEMENT_STATUS_AR.get(status, status),
        'source': src,
        'source_ar': {'admin': 'أسندته الإدارة', 'company': 'اختارته الشركة'}.get(src, '—'),
        'selected': status in ('requested', 'accepted'),
        'accepted': status == 'accepted',
        'can_assign': active is None,               # no pending/accepted request live
        'can_cancel_request': active is not None and active.status == 'requested',
    }


# In-page action/navigation anchors per journey step. Steps where the ADMIN can act
# (subscription/auditor_selection) render a real action button; the rest give the admin
# a "go to section" navigation button so the Next-Best-Action card always routes somewhere.
_ADMIN_STEP_ACTION = {
    'subscription': ('#billing', 'الاشتراك والدفع'),
    'auditor_selection': ('#auditor', 'إسناد مدقق'),
}
# F5: actor-aware next-action routing. Every destination is a section on THIS
# platform-admin page (all @platform_admin_required) — never an auditor-only or
# company-only route. Auditor-owned steps route to the on-page "المدقق" monitoring
# section (#auditor), NOT to the evidence counters (#evidence); the report step routes
# to the readiness/report-status section. Labels distinguish "act" from "monitor".
_ADMIN_STEP_NAV = {
    # admin-owned — a genuinely actionable admin section.
    'email_verification': ('#followup', 'المتابعة والملاحظات'),
    'subscription': ('#billing', 'إدارة الاشتراك'),
    'auditor_selection': ('#auditor', 'إسناد مدقق'),
    # company-owned — a safe monitoring location for the company's own progress.
    'classification': ('#journey', 'متابعة حالة الشركة'),
    'scope_approval': ('#journey', 'متابعة حالة الشركة'),
    'control_plan': ('#journey', 'متابعة حالة الشركة'),
    'evidence': ('#evidence', 'متابعة أدلة الشركة'),
    # auditor-owned — monitor the auditor engagement/progress (admin cannot act).
    'auditor_acceptance': ('#auditor', 'متابعة طلب الإسناد'),
    'evidence_review': ('#auditor', 'متابعة تقدم المدقق'),
    'internal_verdict': ('#auditor', 'متابعة تقدم المدقق'),
    # system/report — monitor readiness/report status (report-status section).
    'readiness_report': ('#evidence', 'متابعة جاهزية التقرير'),
}

# Arabic label for the actor who owns the next step (drives the CTA wording).
_ACTOR_LABEL_AR = {'admin': 'إدارة المنصة', 'company': 'الشركة',
                   'auditor': 'المدقق', 'system': 'النظام'}


def admin_company_journey(company):
    """12-step INTERNAL admin operational journey with per-step status + next action.

    Status per step: completed / needs_action (admin can act now) / waiting (company or
    auditor must act) / locked (blocked by an earlier step). Also returns `next_action`
    (the single recommended thing for the admin to do now). Read-only.
    """
    j = company_journey_summary(company)
    snap = company_operational_snapshot(company)
    eng = admin_auditor_engagement(company)
    # F4: three DISTINCT auditor-review milestones from the centralized state.
    review = auditor_review_state(company)
    try:
        from billing.subscription_access import company_has_active_subscription
        sub_active = bool(company_has_active_subscription(company))
    except Exception:
        sub_active = False

    if eng['status'] == 'requested':
        acceptance_reason = 'بانتظار موافقة المدقق على الطلب.'
    elif eng['last_rejected'] is not None and not eng['selected']:
        acceptance_reason = 'رفض المدقق الطلب — اختر مدققاً آخر أو أعد إرسال الطلب.'
    else:
        acceptance_reason = 'بانتظار اختيار/إسناد مدقق أولاً.'

    # (key, label, done, actor, incomplete_reason)
    step_defs = [
        ('registration', 'إنشاء حساب الشركة', True, 'system', ''),
        ('email_verification', 'التحقق من البريد', j['email_verified'], 'admin',
         'البريد غير موثّق — اطلب من الشركة توثيق البريد أو أعد إرسال رابط التحقق.'),
        ('classification', 'التصنيف', j['classification_done'], 'company',
         'بانتظار إكمال الشركة ملف التصنيف.'),
        ('scope_approval', 'اعتماد النطاق', j['scope_approved'], 'company',
         'بانتظار اعتماد الشركة نطاق الأطر.'),
        ('control_plan', 'خطة الضوابط', j['control_plan_generated'], 'company',
         'بانتظار إنشاء خطة الضوابط بعد اعتماد النطاق.'),
        ('evidence', 'رفع الأدلة', snap['has_evidence'], 'company',
         'بانتظار رفع الشركة للأدلة.'),
        ('subscription', 'تفعيل الاشتراك', sub_active, 'admin',
         'الاشتراك غير مفعّل — فعّل الاشتراك أو أضف دفعة يدوية.'),
        ('auditor_selection', 'اختيار/إسناد المدقق', eng['selected'], 'admin',
         'لا يوجد مدقق — اختر مدققاً أو انتظر اختيار الشركة لمدقق.'),
        ('auditor_acceptance', 'موافقة المدقق', eng['accepted'], 'auditor', acceptance_reason),
        ('evidence_review', 'مراجعة الأدلة', review['review_started'], 'auditor',
         'بانتظار مراجعة المدقق للأدلة.'),
        ('internal_verdict', 'الحكم الداخلي', review['has_final_verdict'], 'auditor',
         'بانتظار الحكم الداخلي من المدقق.'),
        ('readiness_report', 'تقرير الجاهزية', review['has_final_report'], 'system',
         'بانتظار توفّر تقرير الجاهزية بعد المراجعة.'),
    ]

    steps = []
    current_assigned = False
    next_action = None
    for key, label, done, actor, reason in step_defs:
        if done:
            status = 'completed'
            reason_txt = ''
        elif not current_assigned:
            current_assigned = True
            status = 'needs_action' if actor == 'admin' else 'waiting'
            reason_txt = reason
            # Next-Best-Action always routes to the relevant section (real action for
            # admin steps, navigation for company/auditor steps).
            nav_anchor, nav_btn = _ADMIN_STEP_NAV.get(key, (None, None))
            next_action = {
                'key': key, 'label': label, 'reason': reason,
                'actor': actor,
                'actor_label': _ACTOR_LABEL_AR.get(actor, actor),
                'is_actionable_by_admin': actor == 'admin',
                'anchor': nav_anchor,
                'button_label': nav_btn,
            }
        else:
            status = 'locked'
            reason_txt = reason
        anchor, btn = _ADMIN_STEP_ACTION.get(key, (None, None))
        steps.append({
            'key': key, 'label': label, 'status': status, 'actor': actor,
            'reason': reason_txt,
            'action_anchor': anchor if (status == 'needs_action') else None,
            'action_label': btn if (status == 'needs_action') else None,
        })

    if next_action is None:
        next_action = {'key': 'done', 'label': 'اكتمل المسار',
                       'reason': 'اكتملت مراحل رحلة إدارة ملف الشركة الحالية.',
                       'actor': 'system', 'actor_label': _ACTOR_LABEL_AR['system'],
                       'is_actionable_by_admin': False, 'anchor': None, 'button_label': None}
    return {'steps': steps, 'next_action': next_action}


def crm_operational_queues():
    """Overview counts of companies/requests that need an admin action. Read-only."""
    from core.models import Company
    from billing.models import Payment
    from .models import AuditorAssignment
    q = {'companies_no_email_verified': 0, 'companies_no_auditor': 0,
         'auditor_requests_pending': 0, 'manual_payments_pending': 0}
    try:
        q['companies_no_email_verified'] = (
            Company.objects.exclude(users__email_verified=True).distinct().count())
        with_auditor = (AuditorAssignment.objects
                        .filter(status__in=AuditorAssignment.ACTIVE_STATUSES)
                        .values_list('company_id', flat=True))
        q['companies_no_auditor'] = Company.objects.exclude(id__in=list(with_auditor)).count()
        q['auditor_requests_pending'] = AuditorAssignment.objects.filter(status='requested').count()
        q['manual_payments_pending'] = Payment.objects.filter(
            provider='manual', status='pending').count()
    except Exception:
        pass
    return q
