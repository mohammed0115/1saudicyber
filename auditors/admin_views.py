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
        'queues': crm.crm_operational_queues(),
    })


@platform_admin_required
def crm_companies_list(request):
    """Read-only list of all companies with search, status filter, and pagination."""
    from django.db.models import Q
    from django.core.paginator import Paginator
    from core.models import Company
    companies = crm.companies_overview().select_related('crm_profile', 'crm_profile__assigned_staff')
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    if q:
        companies = companies.filter(
            Q(name__icontains=q) | Q(name_ar__icontains=q) | Q(cr_number__icontains=q))
    if status:
        companies = companies.filter(status=status)
    page = Paginator(companies, 25).get_page(request.GET.get('page'))
    return render(request, 'platform_admin/companies_list.html', {
        'companies': page,
        'page_obj': page,
        'q': q,
        'selected_status': status,
        'status_choices': Company.STATUS_CHOICES,
        'total_count': page.paginator.count,
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
        # UAT-PLATFORM-ADMIN-JOURNEY: internal admin journey + auditor engagement.
        'admin_journey': crm.admin_company_journey(company),
        'auditor_engagement': crm.admin_auditor_engagement(company),
        'assignable_auditors': _assignable_auditors(),
        # F1: truthful framework usage vs plan limit (limit is display-only / unenforced).
        'framework_entitlement': crm.company_framework_entitlement(company),
        # F-AUDIT A1: controls where the parallel auditor-verdict silos disagree (read-only).
        'verdict_disagreements': _verdict_disagreements(company),
        # H4 — audit findings + maturity oversight for this company.
        **_audit_oversight(company),
    })


def _audit_oversight(company):
    """H4 — read-only findings summary + latest-assessment maturity for the admin console."""
    from auditor_portal.models import AuditFinding
    from auditor_portal.findings_service import assessment_maturity
    from compliance.models import Assessment
    findings = list(AuditFinding.objects.filter(company_control__company=company)
                    .select_related('company_control__control')[:50])
    latest = Assessment.objects.filter(company=company).order_by('-created_at').first()
    return {
        'audit_findings': findings,
        'audit_open_findings': sum(1 for f in findings if f.is_open),
        'audit_maturity': assessment_maturity(latest) if latest else None,
    }


def _verdict_disagreements(company):
    """F-AUDIT A1: read-only oversight — controls whose auditor-verdict silos conflict."""
    from compliance.verdict_resolver import company_verdict_disagreements
    return company_verdict_disagreements(company)


def _assignable_auditors():
    from . import services as auditor_services
    return auditor_services.list_available_auditors().select_related('user')


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


# ------------------------------------------------------------
# UAT-PLATFORM-ADMIN-JOURNEY — admin-initiated auditor engagement (staff-only).
# Reuses the auditors.services layer (no new model). Assignment counts only once
# an auditor ACCEPTS; admin assignment just creates the request as the admin.
# ------------------------------------------------------------
@platform_admin_required
@require_http_methods(["POST"])
def crm_assign_auditor(request, company_id):
    """POST-only: admin assigns an ACTIVE auditor to a company (creates a request).
    Prevents a duplicate active request. The auditor still must accept."""
    from core.models import Company
    from . import services as auditor_services
    from .models import AuditorProfile
    company = get_object_or_404(Company, id=company_id)
    auditor = AuditorProfile.objects.filter(id=request.POST.get('auditor_id') or 0).first()
    if auditor is None:
        messages.error(request, 'المدقق غير موجود.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    if auditor.status != 'active' or not auditor.is_available:
        messages.error(request, 'لا يمكن إسناد مدقق غير مفعّل أو غير متاح.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    assignment, created = auditor_services.create_assignment(
        company, auditor, requested_by=request.user,
        notes=(request.POST.get('reason', '') or '').strip())
    if not created and assignment is not None:
        messages.info(request, 'يوجد بالفعل طلب/إسناد مدقق نشط لهذه الشركة.')
    elif assignment is None:
        messages.error(request, 'تعذّر إسناد المدقق.')
    else:
        crm._crm_audit(request.user, 'admin_auditor_assigned', company,
                       extra={'auditor_id': auditor.id, 'assignment_id': assignment.id})
        messages.success(request, 'تم إسناد المدقق. بانتظار موافقة المدقق على الطلب.')
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
@require_http_methods(["POST"])
def crm_cancel_auditor_request(request, company_id):
    """POST-only: admin cancels the company's PENDING auditor request. Reason required."""
    from core.models import Company
    from . import services as auditor_services
    company = get_object_or_404(Company, id=company_id)
    reason = (request.POST.get('reason', '') or '').strip()
    if not reason:
        messages.error(request, 'السبب مطلوب لإلغاء طلب المدقق.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    assignment = auditor_services.company_active_assignment(company)
    if assignment is None or assignment.status != 'requested':
        messages.error(request, 'لا يوجد طلب مدقق قيد الانتظار لإلغائه.')
        return redirect('platform_admin:company_detail', company_id=company.id)
    if auditor_services.cancel_assignment(assignment, by=request.user):
        assignment.response_note = reason[:2000]
        assignment.responded_by = request.user
        assignment.save(update_fields=['response_note', 'responded_by', 'updated_at'])
        crm._crm_audit(request.user, 'admin_auditor_request_cancelled', company,
                       extra={'assignment_id': assignment.id, 'reason': reason[:500]})
        messages.success(request, 'تم إلغاء طلب المدقق.')
    return redirect('platform_admin:company_detail', company_id=company.id)


@platform_admin_required
def crm_auditor_requests(request):
    """Read-only global list of all company↔auditor requests (staff-only)."""
    status = request.GET.get('status', 'all')
    qs = (AuditorAssignment.objects
          .select_related('company', 'auditor', 'auditor__user', 'requested_by')
          .order_by('-requested_at'))
    valid = {k for k, _ in AuditorAssignment.STATUS_CHOICES}
    if status in valid:
        qs = qs.filter(status=status)
    else:
        status = 'all'
    return render(request, 'platform_admin/auditor_requests.html', {
        'requests': qs, 'selected_status': status,
        'status_choices': AuditorAssignment.STATUS_CHOICES,
    })


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


@platform_admin_required
def crm_rfi_dashboard(request):
    """Central cross-company RFI dashboard for platform admin (read-only monitoring).

    Aggregates every DocumentRequest (RFI) across companies with status buckets and
    overdue highlighting. Admin monitors — it never issues or alters an auditor verdict.
    """
    from auditor_portal.models import DocumentRequest
    from django.utils import timezone
    import datetime as _dt

    status = request.GET.get('status', '')
    base = DocumentRequest.objects.select_related(
        'assessment__company', 'company_control__control', 'auditor')
    qs = base.filter(status=status) if status else base
    rows = list(qs.order_by('-created_at')[:300])

    today = timezone.now().date()
    for r in rows:
        r.is_overdue = bool(r.due_date and r.due_date < today and r.status in DocumentRequest.OPEN_STATES)
        r.age_days = (today - r.created_at.date()).days if r.created_at else 0

    counts = {
        'open': base.filter(status='open').count(),
        'responded': base.filter(status='responded').count(),
        'under_review': base.filter(status='under_review').count(),
        'closed': base.filter(status='closed').count(),
        'total': base.count(),
        'overdue': base.filter(status__in=DocumentRequest.OPEN_STATES,
                               due_date__lt=today).count(),
    }
    return render(request, 'platform_admin/rfi_dashboard.html', {
        'rows': rows, 'counts': counts, 'selected_status': status,
    })


@platform_admin_required
def crm_messages(request):
    """Central inbox of all company message threads for platform admin.

    Read-only overview so admins can find and open any conversation (fixes the
    'admin lands on the wrong/empty thread' gap). Access to each thread is still
    enforced by messaging.can_access_thread on the thread view itself.
    """
    from django.db.models import Max, Count
    from auditor_portal.models import CompanyMessage
    from core.models import Company
    agg = (CompanyMessage.objects.values('company')
           .annotate(last=Max('created_at'), cnt=Count('id')).order_by('-last')[:100])
    company_map = {c.id: c for c in Company.objects.filter(id__in=[a['company'] for a in agg])}
    rows = []
    for a in agg:
        company = company_map.get(a['company'])
        if not company:
            continue
        last_msg = (CompanyMessage.objects.filter(company_id=a['company'])
                    .select_related('sender').order_by('-created_at').first())
        rows.append({'company': company, 'count': a['cnt'], 'last_at': a['last'], 'last': last_msg})
    return render(request, 'platform_admin/messages.html', {'rows': rows})
