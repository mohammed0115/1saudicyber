"""Phase 8D-3B-AUTH-A — email OTP service (generate / hash / verify / resend).

Safe by design:
  * 6-digit numeric code, generated with the `secrets` CSPRNG.
  * Stored only as a salted hash (Django password hasher) — never plaintext.
  * Expires after OTP_TTL_MINUTES; allows at most OTP_MAX_ATTEMPTS verifications.
  * Resend is throttled to one code per OTP_RESEND_INTERVAL_SECONDS.
  * Verifying never reveals the code; emails contain only the code the user owns.

No official certification/accreditation wording. Branding: 1SaudiCyber, operated
by Get Solution Company.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_INTERVAL_SECONDS = 60
OTP_PURPOSE_EMAIL = 'email_verify'


def generate_code():
    """A 6-digit numeric code as a zero-padded string (CSPRNG)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _latest_active(user, purpose=OTP_PURPOSE_EMAIL):
    from .models import EmailOTP
    return (EmailOTP.objects.filter(user=user, purpose=purpose, used=False)
            .order_by('-created_at').first())


def issue_otp(user, purpose=OTP_PURPOSE_EMAIL):
    """Invalidate prior unused OTPs and create a fresh one. Returns (otp, raw_code).

    The raw code is returned ONLY so the caller can email it; it is never stored.
    """
    from .models import EmailOTP
    EmailOTP.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
    raw = generate_code()
    otp = EmailOTP.objects.create(
        user=user, purpose=purpose,
        code_hash=make_password(raw),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    return otp, raw


def can_resend(user, purpose=OTP_PURPOSE_EMAIL):
    """True if enough time has passed since the last issued OTP (throttle)."""
    otp = _latest_active(user, purpose)
    if otp is None:
        return True
    elapsed = (timezone.now() - otp.created_at).total_seconds()
    return elapsed >= OTP_RESEND_INTERVAL_SECONDS


def send_otp_email(user, raw_code):
    """Send the branded OTP email via the configured Django email backend."""
    subject = 'رمز التحقق من بريدك الإلكتروني · 1SaudiCyber'
    body = (
        f"مرحبًا،\n\n"
        f"رمز التحقق الخاص بك في منصة 1SaudiCyber هو: {raw_code}\n"
        f"ينتهي هذا الرمز خلال {OTP_TTL_MINUTES} دقائق ولا تشاركه مع أي أحد.\n\n"
        f"Your 1SaudiCyber email verification code is: {raw_code}\n"
        f"It expires in {OTP_TTL_MINUTES} minutes. Do not share it with anyone.\n\n"
        f"منصة 1SaudiCyber مملوكة ومُدارة بواسطة شركة احصل الحل.\n"
        f"1SaudiCyber is owned and operated by Get Solution Company.\n"
    )
    send_mail(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@1saudicyber.com'),
              [user.email], fail_silently=True)


def issue_and_send(user, purpose=OTP_PURPOSE_EMAIL):
    """Convenience: issue an OTP and email it. Returns the raw code (for tests/dev)."""
    otp, raw = issue_otp(user, purpose)
    send_otp_email(user, raw)
    return raw


def verify_otp(user, code, purpose=OTP_PURPOSE_EMAIL):
    """Verify a submitted code. Returns (ok: bool, reason: str).

    reason in {'verified','no_otp','expired','too_many_attempts','invalid'}.
    On success, marks the OTP used and sets user.email_verified=True.
    """
    code = (code or '').strip()
    otp = _latest_active(user, purpose)
    if otp is None:
        return False, 'no_otp'
    if otp.is_expired():
        return False, 'expired'
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        return False, 'too_many_attempts'

    if not code.isdigit() or not check_password(code, otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            return False, 'too_many_attempts'
        return False, 'invalid'

    otp.used = True
    otp.save(update_fields=['used'])
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])
    return True, 'verified'
