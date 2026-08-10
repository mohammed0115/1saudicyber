"""
DD-fix (commercial) — team invite service.

A company_admin/admin invites a teammate by email + role; an emailed token link lets the
invitee set a password and join THAT company (tenant-bound). No cross-tenant escalation:
the role is clamped to non-privileged company roles, never 'admin'/'auditor'.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

# Roles a company admin may grant to a teammate (never platform admin or auditor).
INVITABLE_ROLES = ['company_admin', 'compliance_officer', 'it_security', 'bu_manager', 'executive']
INVITE_TTL_DAYS = 7


def create_invite(company, email, role, invited_by):
    """Create (or refresh) a pending invite for email→company with a safe role."""
    from .models import UserInvite, User
    email = (email or '').strip().lower()
    if not email:
        raise ValueError('email required')
    if role not in INVITABLE_ROLES:
        role = 'compliance_officer'
    if User.objects.filter(email=email).exists():
        raise ValueError('a user with this email already exists')
    invite = UserInvite.objects.create(
        company=company, email=email, role=role, invited_by=invited_by,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(days=INVITE_TTL_DAYS))
    _email_invite(invite)
    return invite


def _email_invite(invite):
    frm = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@cyber-5.com')
    # Absolute link so the emailed invite is clickable from outside the app. SITE_URL is the
    # single source of truth for the public base URL (same pattern as the email-verification
    # link in core.services); this is not a second URL-building mechanism.
    link = f"{settings.SITE_URL}/invite/{invite.token}/"
    body = ('تمت دعوتك للانضمام إلى فريق «%s» على منصة 1SaudiCyber.\n\n'
            'لإكمال الانضمام وتعيين كلمة المرور، افتح الرابط:\n'
            '%s\n\nالرابط صالح لمدة %d أيام.'
            % (invite.company.name, link, INVITE_TTL_DAYS))
    try:
        send_mail('دعوة للانضمام إلى فريق منشأتك', body, frm, [invite.email], fail_silently=True)
    except Exception:
        pass


def accept_invite(invite, *, first_name, last_name, password):
    """Create the user for a valid invite, bound to the invite's company + role."""
    from .models import User
    if not invite.is_valid():
        raise ValueError('invite is not valid')
    user = User.objects.create_user(
        email=invite.email, password=password, role=invite.role,
        company=invite.company, first_name=(first_name or '').strip(),
        last_name=(last_name or '').strip(), email_verified=True)
    invite.status = 'accepted'
    invite.accepted_at = timezone.now()
    invite.save(update_fields=['status', 'accepted_at'])
    return user
