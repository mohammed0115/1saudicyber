"""Phase 8D-3A — Get Solution platform-admin auditor approval service.

Deterministic, safe state transitions for AuditorProfile, with durable audit
logging via the existing core.AuditLog model (NO new model / NO migration).

Status mapping (reuses the existing AuditorProfile.STATUS_CHOICES — there is no
separate 'rejected' status, so a declined/rejected auditor is recorded as
'inactive', following existing conventions):

    approve     -> active
    reject      -> inactive   (reason required)
    suspend     -> suspended  (reason required)
    reactivate  -> active

The platform (1SaudiCyber) is owned and operated by Get Solution Company
(شركة احصل الحل). This is an INTERNAL operational workflow only; it never issues
any official certification or accreditation.
"""

# action -> transition spec.
TRANSITIONS = {
    'approve':    {'to': 'active',    'from': {'pending_review', 'inactive', 'suspended'}, 'reason_required': False},
    'reject':     {'to': 'inactive',  'from': {'pending_review', 'active', 'suspended'},    'reason_required': True},
    'suspend':    {'to': 'suspended', 'from': {'active', 'pending_review'},                 'reason_required': True},
    'reactivate': {'to': 'active',    'from': {'suspended', 'inactive'},                    'reason_required': False},
}

ACTION_LABELS_AR = {
    'approve': 'اعتماد وتفعيل',
    'reject': 'رفض',
    'suspend': 'إيقاف مؤقت',
    'reactivate': 'إعادة تفعيل',
}


class AuditorAdminError(Exception):
    """Raised for an invalid admin action (permission/transition/reason)."""


def is_platform_admin(user):
    """Get Solution platform admin: an authenticated staff or superuser.

    Reuses the project's existing staff/superuser convention; never weakens it.
    """
    return bool(getattr(user, 'is_authenticated', False)
                and (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)))


def pending_auditors():
    from .models import AuditorProfile
    return AuditorProfile.objects.filter(status='pending_review')


def status_summary():
    """Counts per status for the admin summary cards. Read-only."""
    from .models import AuditorProfile
    from django.db.models import Count
    base = {'pending_review': 0, 'active': 0, 'suspended': 0, 'inactive': 0}
    for row in AuditorProfile.objects.values('status').annotate(n=Count('id')):
        base[row['status']] = row['n']
    base['total'] = sum(base[k] for k in ('pending_review', 'active', 'suspended', 'inactive'))
    return base


def _record_audit(admin_user, profile, action, old_status, new_status, reason):
    """Durably record the admin action in core.AuditLog (no migration needed)."""
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=admin_user if getattr(admin_user, 'is_authenticated', False) else None,
            action=f'auditor_{action}'[:100],
            path='/platform-admin/auditors/',
            metadata={
                'auditor_profile_id': profile.id,
                'auditor_user_id': profile.user_id,
                'auditor_email': getattr(profile.user, 'email', ''),
                'old_status': old_status,
                'new_status': new_status,
                'reason': (reason or '')[:1000],
                'performed_by': getattr(admin_user, 'email', ''),
            },
        )
    except Exception:
        # Audit logging must never block the operational action.
        pass


def apply_auditor_action(profile, action, admin_user, reason=''):
    """Validate + apply an admin action to an AuditorProfile. Returns the new status.

    Raises AuditorAdminError on permission, unknown action, illegal transition,
    or a missing required reason. Writes a durable AuditLog entry on success.
    """
    if not is_platform_admin(admin_user):
        raise AuditorAdminError('ليست لديك صلاحية إدارة اعتماد المدققين.')
    spec = TRANSITIONS.get(action)
    if spec is None:
        raise AuditorAdminError('إجراء غير معروف.')
    reason = (reason or '').strip()
    if spec['reason_required'] and not reason:
        raise AuditorAdminError('يجب إدخال سبب لهذا الإجراء.')
    old_status = profile.status
    if old_status not in spec['from']:
        raise AuditorAdminError('لا يمكن تنفيذ هذا الإجراء على الحالة الحالية للحساب.')
    new_status = spec['to']
    profile.status = new_status
    profile.save(update_fields=['status', 'updated_at'])
    _record_audit(admin_user, profile, action, old_status, new_status, reason)
    return new_status
