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
from django.db import transaction
from django.utils import timezone

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


def _record_audit(admin_user, profile, action, old_status, new_status, reason,
                  *, revoked_ids=None, revoked_old=None, user_login_disabled=False):
    """Durably record the admin action in core.AuditLog (no migration needed).

    Records who/target/old+new profile status/reason AND — for de-provisioning actions — the
    exact assignments revoked (ids + their prior states) and whether the login was disabled, so
    the security decision is fully reconstructable. Called INSIDE the transaction as the last
    step, so a rollback removes this row too (no success record without a committed change).
    """
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
                'revoked_assignment_ids': list(revoked_ids or []),
                'revoked_assignment_count': len(revoked_ids or []),
                'revoked_assignment_old_states': dict(revoked_old or {}),
                'user_login_disabled': bool(user_login_disabled),
            },
        )
    except Exception:
        # Audit logging must never block the operational action.
        pass


def apply_auditor_action(profile, action, admin_user, reason=''):
    """Validate + apply an admin action to an AuditorProfile atomically. Returns the new status.

    Raises AuditorAdminError on permission, unknown action, illegal transition, or a missing
    required reason. The whole change is fail-closed and atomic (transaction.atomic):

      * De-provisioning (suspend/reject → a non-'active' status) does ALL of the following or
        NONE — profile status change, revocation of every LIVE assignment (requested/accepted →
        'cancelled'), and disabling the auditor-only login (user.is_active=False). No stale
        'accepted' row and no live session can keep a de-provisioned auditor in.
      * Re-provisioning (approve/reactivate → 'active') re-enables the login but does NOT
        auto-restore revoked assignments — the company must be re-assigned explicitly.

    Idempotent: the TRANSITIONS 'from' guard rejects repeat actions on a terminal status, and
    the assignment revocation filters on live statuses (a second run finds none). The AuditLog
    row is written INSIDE the transaction, so a rollback leaves no success record.
    """
    if not is_platform_admin(admin_user):
        raise AuditorAdminError('ليست لديك صلاحية إدارة اعتماد المدققين.')
    spec = TRANSITIONS.get(action)
    if spec is None:
        raise AuditorAdminError('إجراء غير معروف.')
    reason = (reason or '').strip()
    if spec['reason_required'] and not reason:
        raise AuditorAdminError('يجب إدخال سبب لهذا الإجراء.')

    from .models import AuditorProfile, AuditorAssignment

    with transaction.atomic():
        # Lock the profile row (PostgreSQL) so concurrent admin actions serialize; on SQLite
        # select_for_update is a no-op but transaction.atomic still makes the change all-or-nothing.
        locked = AuditorProfile.objects.select_for_update().select_related('user').get(pk=profile.pk)
        old_status = locked.status
        if old_status not in spec['from']:
            raise AuditorAdminError('لا يمكن تنفيذ هذا الإجراء على الحالة الحالية للحساب.')
        new_status = spec['to']
        locked.status = new_status
        locked.save(update_fields=['status', 'updated_at'])

        revoked_ids, revoked_old, user_login_disabled = [], {}, False
        user = locked.user
        if new_status != 'active':
            # Revoke every LIVE assignment (requested + accepted) — fail-closed de-provisioning.
            live = (AuditorAssignment.objects.select_for_update()
                    .filter(auditor=locked, status__in=AuditorAssignment.ACTIVE_STATUSES))
            for asg in live:
                revoked_ids.append(asg.id)
                revoked_old[str(asg.id)] = asg.status
                asg.status = 'cancelled'
                asg.response_note = (('[de-provisioned:%s] ' % action) + (asg.response_note or ''))[:2000]
                asg.responded_by = admin_user if getattr(admin_user, 'is_authenticated', False) else None
                asg.responded_at = timezone.now()
                asg.save(update_fields=['status', 'response_note', 'responded_by',
                                        'responded_at', 'updated_at'])
            # Auditor accounts are auditor-only (platform-side; no company link, role='auditor').
            # Disabling the login terminates any existing session on the next request (Django's
            # get_user() resolves an inactive user to AnonymousUser). Never touch a staff/superuser
            # account (defensive: an auditor should never be one).
            if user is not None and user.is_active and not (user.is_staff or user.is_superuser):
                user.is_active = False
                user.save(update_fields=['is_active'])
                user_login_disabled = True
        else:
            # Re-provisioning: restore login only. Assignments stay revoked (explicit re-assign).
            if user is not None and not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])

        _record_audit(admin_user, locked, action, old_status, new_status, reason,
                      revoked_ids=revoked_ids, revoked_old=revoked_old,
                      user_login_disabled=user_login_disabled)

    # Keep the caller's in-memory object consistent with the committed change.
    profile.status = new_status
    return new_status
