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
