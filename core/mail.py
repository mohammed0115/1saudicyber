"""Single choke point for outbound mail — best-effort delivery, never-silent failure.

Every caller in the platform previously passed ``fail_silently=True`` straight to
``django.core.mail.send_mail``. That kept signup/OTP/invite flows from 500-ing when SMTP
was down, which is correct — but it also swallowed the SMTP error itself, so a fully
broken mail configuration looked identical to a working one from inside the app. A
sender-domain rejection went unnoticed in production for exactly this reason.

``send_mail_logged`` keeps the non-blocking behaviour (it never raises) and adds the
missing half: the provider's error is logged with the recipients and the failing
subject, so "no email arrived" is diagnosable from the application log alone.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def default_from():
    """The configured envelope sender, with the same fallback used across the app."""
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@cyber-5.com')


def send_mail_logged(subject, message, recipient_list, *, from_email=None):
    """Send one message best-effort. Returns the number delivered (0 on failure).

    Never raises: a mail outage must not block the action that triggered the mail
    (issuing an OTP, recording a finding, creating an invite). Unlike ``fail_silently``,
    the underlying SMTP error IS logged at ERROR with enough context to act on.
    """
    to = sorted({e for e in recipient_list if e})
    if not to:
        return 0
    try:
        return send_mail(subject, message, from_email or default_from(), to,
                         fail_silently=False)
    except Exception:
        logger.exception('Email delivery failed | subject=%r | to=%s', subject, ', '.join(to))
        return 0
