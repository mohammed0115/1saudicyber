"""Phase 8D-3A — Get Solution platform-admin auditor approval views.

Internal operational area for the 1SaudiCyber platform admin (Get Solution
Company / شركة احصل الحل) to review and act on auditor accounts. Access is
restricted to authenticated staff/superuser; company users, auditor users, and
anonymous visitors are denied. Read-only listing + POST-only state changes.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import AuditorProfile, AuditorAssignment
from . import admin_services as svc
from . import crm_services as crm


def platform_admin_required(view):
    """Allow only authenticated staff/superuser (Get Solution platform admin)."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not getattr(user, 'is_authenticated', False):
            return redirect('/login/?next=' + request.path)
        if not svc.is_platform_admin(user):
            return render(request, 'platform_admin/denied.html', status=403)
        return view(request, *args, **kwargs)
    return _wrapped


@platform_admin_required
def auditor_approval_list(request):
    """Pending-first list of auditors with summary cards and a status filter."""
    status = request.GET.get('status', 'pending_review')
    qs = AuditorProfile.objects.select_related('user').order_by('-created_at')
    valid_statuses = {k for k, _ in AuditorProfile.STATUS_CHOICES}
    if status in valid_statuses:
        qs = qs.filter(status=status)
    else:
        status = 'all'
    return render(request, 'platform_admin/auditor_list.html', {
        'auditors': qs,
        'summary': svc.status_summary(),
        'selected_status': status,
        'status_choices': AuditorProfile.STATUS_CHOICES,
    })


@platform_admin_required
def auditor_approval_detail(request, profile_id):
    """Full auditor profile + available admin actions (with confirmation)."""
    profile = get_object_or_404(AuditorProfile.objects.select_related('user'), id=profile_id)
    # Which actions are valid from the current status (drives the confirm UI).
    available = [
        {'action': a, 'label': svc.ACTION_LABELS_AR[a],
         'reason_required': spec['reason_required']}
        for a, spec in svc.TRANSITIONS.items() if profile.status in spec['from']
    ]
    return render(request, 'platform_admin/auditor_detail.html', {
        'profile': profile,
        'available_actions': available,
        'company_requests': AuditorAssignment.objects.filter(auditor=profile)
            .select_related('company').order_by('-requested_at'),
    })


# ============================================================
# Phase 8D-3B-ADMIN-CRM-A — Get Solution CRM Console (read-only foundation)
# ============================================================
@platform_admin_required
def crm_dashboard(request):
    """Internal Get Solution operations console home: summary + navigation."""
    return render(request, 'platform_admin/dashboard.html', {
        'summary': crm.crm_summary(),
        'data_health': crm.platform_data_health(),
    })


@platform_admin_required
def crm_companies_list(request):
    """Read-only list of all companies with linked-user counts and CRM status."""
    companies = crm.companies_overview().select_related('crm_profile', 'crm_profile__assigned_staff')
    return render(request, 'platform_admin/companies_list.html', {
        'companies': companies,
    })


@platform_admin_required
def crm_company_detail(request, company_id):
    """Operational snapshot + CRM follow-up (status, notes, timeline) + link/unlink."""
    from core.models import Company
    from .models import CompanyCRMProfile
    company = get_object_or_404(Company, id=company_id)
    return render(request, 'platform_admin/company_detail.html', {
        'company': company,
        'snapshot': crm.company_operational_snapshot(company),
        'journey': crm.company_journey_summary(company),
        'linkable_users': crm.linkable_users(),
        'crm_profile': crm.get_company_crm_profile(company),
        'crm_notes': crm.company_notes(company),
        'crm_timeline': crm.get_company_activity_timeline(company),
        'crm_status_choices': CompanyCRMProfile.CRM_STATUS_CHOICES,
        'assignable_staff': crm.assignable_staff(),
        'evidence_summary': crm.company_evidence_summary(company),
        'gap_summary': crm.company_gap_summary(company),
        'risk_summary': crm.company_risk_summary(company),
        'report_summary': crm.company_report_summary(company),
        'subscription_summary': crm.company_subscription_summary(company),
        'feature_summary': _plan_feature_summary(company),
        'auditor_requests': AuditorAssignment.objects.filter(company=company)
            .select_related('auditor', 'auditor__user').order_by('-requested_at'),
        'manual_payments': _manual_payments(company),
        'billing_plans': _active_plans(),
    })


def _manual_payments(company):
    from billing.models import Payment
    return (Payment.objects.filter(company=company, provider='manual')
            .select_related('created_by').order_by('-created_at')[:20])


def _active_plans():
    from billing import subscription_services as bsvc
    return bsvc.active_plans()


def _plan_feature_summary(company):
    """Safe plan feature/usage summary for CRM (no secrets, no card data)."""
    from billing.access import plan_feature_summary
    return plan_feature_summary(company)


@platform_admin_required
@require_http_methods(["POST"])
def crm_subscription_action(request, company_id):
    """POST-only: staff subscription action (activate / cancel / start_trial). Reason required
    for activate/cancel. Tenant-safe; audited via the billing service layer."""
    from core.models import Company
    from billing import subscription_services as bsvc
    company = get_object_or_404(Company, id=company_id)
    action = request.POST.get('action', '')
    reason = (request.POST.get('reason', '') or '').strip()
    sub = bsvc.get_current_subscription(company)
    if action in ('activate', 'cancel') and not reason:
        messages.error(request, 'السبب مطلوب لهذا الإجراء · Reason required for this action.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    if action == 'activate':
        from billing.models import Payment
        # BUG-2: confirming an already-active subscription must NOT extend it again.
        if sub is not None and sub.status == 'active' and sub.is_active():
            messages.info(request, 'الاشتراك مُفعّل بالفعل · Subscription is already active.')
        else:
            # BUG-3: confirm the pending MANUAL payment (marks it paid AND activates the
            # subscription), so no stale 'under review' banner remains. Falls back to a
            # plain activation only when there is no pending manual payment to confirm.
            pending = (Payment.objects.filter(company=company, subscription=sub,
                                              status='pending', provider='manual')
                       .order_by('-created_at').first())
            if pending is not None:
                bsvc.mark_payment_paid(pending, actor=request.user, reason=reason)
            else:
                bsvc.activate_subscription(sub, actor=request.user, reason=reason)
            messages.success(request, 'تم تفعيل الاشتراك وتأكيد الدفع اليدوي.')
    elif action == 'cancel':
        bsvc.cancel_subscription(sub, actor=request.user, reason=reason)
        # Reject flow: clear any stale pending manual payment (does not activate).
        bsvc.cancel_pending_manual_payments(company, sub, actor=request.user, reason=reason)
        messages.success(request, 'تم إلغاء الاشتراك · Subscription cancelled.')
    elif action == 'start_trial':
        bsvc.start_trial(company, bsvc.get_plan('trial'), actor=request.user)
        messages.success(request, 'تم بدء الفترة التجريبية · Trial started.')
    else:
        messages.error(request, 'إجراء غير معروف · Unknown action.')
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_add_manual_payment(request, company_id):
    """POST-only: add a PENDING manual payment (never activates). Reason required. Staff-only."""
    from core.models import Company
    from billing import subscription_services as bsvc
    company = get_object_or_404(Company, id=company_id)
    reason = (request.POST.get('reason', '') or '').strip()
    if not reason:
        messages.error(request, 'السبب مطلوب لإضافة دفعة يدوية · Reason required.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    try:
        bsvc.add_manual_payment(company, bsvc.get_plan(request.POST.get('plan', '')),
                                request.POST.get('amount', '0'), actor=request.user,
                                reference=request.POST.get('reference', ''), note=reason)
        messages.success(request, 'تمت إضافة الدفعة اليدوية بانتظار التأكيد.')
    except bsvc.SubscriptionError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_confirm_manual_payment(request, company_id, payment_id):
    """POST-only: confirm a company's OWN pending manual payment -> activate subscription."""
    from core.models import Company
    from billing import subscription_services as bsvc
    from billing.models import Payment
    company = get_object_or_404(Company, id=company_id)
    reason = (request.POST.get('reason', '') or '').strip()
    payment = Payment.objects.filter(id=payment_id, company=company).first()
    if payment is None:
        messages.error(request, 'الدفعة غير موجودة أو لا تخصّ هذه الشركة.')
    elif not reason:
        messages.error(request, 'السبب مطلوب لتأكيد الدفعة · Reason required.')
    else:
        try:
            bsvc.confirm_manual_payment(payment, actor=request.user, reason=reason)
            messages.success(request, 'تم تأكيد الدفعة اليدوية وتفعيل الاشتراك.')
        except bsvc.SubscriptionError as e:
            messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_reject_manual_payment(request, company_id, payment_id):
    """POST-only: reject a company's OWN pending manual payment. Never activates."""
    from core.models import Company
    from billing import subscription_services as bsvc
    from billing.models import Payment
    company = get_object_or_404(Company, id=company_id)
    reason = (request.POST.get('reason', '') or '').strip()
    payment = Payment.objects.filter(id=payment_id, company=company).first()
    if payment is None:
        messages.error(request, 'الدفعة غير موجودة أو لا تخصّ هذه الشركة.')
    elif not reason:
        messages.error(request, 'السبب مطلوب لرفض الدفعة · Reason required.')
    else:
        try:
            bsvc.reject_manual_payment(payment, actor=request.user, reason=reason)
            messages.success(request, 'تم رفض الدفعة اليدوية.')
        except bsvc.SubscriptionError as e:
            messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_add_note(request, company_id):
    """POST-only: add an internal CRM note to a company (staff-only)."""
    from core.models import Company
    company = get_object_or_404(Company, id=company_id)
    try:
        crm.add_company_note(request.user, company, request.POST.get('text', ''))
        messages.success(request, 'تمت إضافة الملاحظة الداخلية.')
    except crm.CRMLinkError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_update_status(request, company_id):
    """POST-only: update a company's internal CRM follow-up status (staff-only)."""
    from core.models import Company
    company = get_object_or_404(Company, id=company_id)
    try:
        crm.update_company_crm_status(
            request.user, company,
            crm_status=request.POST.get('crm_status'),
            assigned_staff_id=request.POST.get('assigned_staff_id') or 0,
            next_follow_up_date=request.POST.get('next_follow_up_date') or None,
            internal_summary=request.POST.get('internal_summary'),
            reason=request.POST.get('reason', ''))
        messages.success(request, 'تم تحديث حالة المتابعة.')
    except crm.CRMLinkError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_link_user(request, company_id):
    """POST-only: link an existing unlinked user to this company (staff-only)."""
    from core.models import Company, User
    company = get_object_or_404(Company, id=company_id)
    user = User.objects.filter(id=request.POST.get('user_id') or 0).first()
    try:
        crm.link_user_to_company(request.user, user, company, request.POST.get('reason', ''))
        messages.success(request, 'تم ربط الحساب %s بالشركة %s.' % (
            getattr(user, 'email', ''), company.name))
    except crm.CRMLinkError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_unlink_user(request, company_id):
    """POST-only: unlink a user from this company (staff-only). Deletes nothing."""
    from core.models import Company, User
    company = get_object_or_404(Company, id=company_id)
    user = User.objects.filter(id=request.POST.get('user_id') or 0, company=company).first()
    try:
        crm.unlink_user_from_company(request.user, user, request.POST.get('reason', ''))
        messages.success(request, 'تم إلغاء ربط الحساب %s.' % getattr(user, 'email', ''))
    except crm.CRMLinkError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
def crm_unlinked_accounts(request):
    """Accounts not linked to any company/auditor profile (explains 'No Company Associated')."""
    return render(request, 'platform_admin/unlinked_accounts.html', {
        'users': crm.unlinked_users(),
    })


@platform_admin_required
@require_http_methods(["POST"])
def auditor_approval_action(request, profile_id):
    """Apply an admin action (approve/reject/suspend/reactivate). POST-only."""
    profile = get_object_or_404(AuditorProfile.objects.select_related('user'), id=profile_id)
    action = request.POST.get('action', '')
    reason = request.POST.get('reason', '')
    try:
        new_status = svc.apply_auditor_action(profile, action, request.user, reason=reason)
        messages.success(
            request, 'تم تنفيذ الإجراء "%s". الحالة الجديدة: %s.'
            % (svc.ACTION_LABELS_AR.get(action, action), profile.get_status_display()))
    except svc.AuditorAdminError as e:
        messages.error(request, str(e))
    return redirect('platform_admin:auditor_detail', profile_id=profile.id)
