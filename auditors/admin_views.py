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

from .models import AuditorProfile
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
    })


# ============================================================
# Phase 8D-3B-ADMIN-CRM-A — Get Solution CRM Console (read-only foundation)
# ============================================================
@platform_admin_required
def crm_dashboard(request):
    """Internal Get Solution operations console home: summary + navigation."""
    return render(request, 'platform_admin/dashboard.html', {
        'summary': crm.crm_summary(),
    })


@platform_admin_required
def crm_companies_list(request):
    """Read-only list of all companies with linked-user counts and status."""
    return render(request, 'platform_admin/companies_list.html', {
        'companies': crm.companies_overview(),
    })


@platform_admin_required
def crm_company_detail(request, company_id):
    """Read-only operational snapshot for one company + link/unlink actions."""
    from core.models import Company
    company = get_object_or_404(Company, id=company_id)
    return render(request, 'platform_admin/company_detail.html', {
        'company': company,
        'snapshot': crm.company_operational_snapshot(company),
        'linkable_users': crm.linkable_users(),
    })


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
