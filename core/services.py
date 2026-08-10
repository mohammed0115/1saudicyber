"""Core services: email (verification, alerts) and MFA (TOTP)."""
from django.conf import settings
from django.core.mail import send_mail


def send_verification_email(user):
    """FR-002.8: send a one-time email-verification link."""
    from core.models import EmailVerificationToken
    token = EmailVerificationToken.objects.create(user=user, token=EmailVerificationToken.generate())
    link = f"{settings.SITE_URL}/verify-email/{token.token}/"
    send_mail(
        subject='Verify your CyberTrust KSA account',
        message=(f'Welcome to CyberTrust KSA.\n\nPlease verify your email:\n{link}\n\n'
                 f'مرحبًا بك في CyberTrust KSA. يرجى تأكيد بريدك عبر الرابط أعلاه.'),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
    return token


def send_alert_email(alert):
    """FR-010.5: email a critical/high compliance alert to the company admins."""
    from core.models import User
    recipients = list(
        User.objects.filter(company=alert.company, role__in=['company_admin', 'compliance_officer'])
        .values_list('email', flat=True)
    )
    if not recipients:
        return False
    send_mail(
        subject=f'[CyberTrust KSA] {alert.get_severity_display()} alert: {alert.title}',
        message=f'{alert.title}\n\n{alert.description}\n\n{alert.title_ar}\n{alert.description_ar}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=True,
    )
    return True


# ---- MFA (TOTP) ----

def mfa_provisioning_uri(user):
    """Generate (and persist if needed) a TOTP secret and return the otpauth URI for a QR code.

    The secret is stored encrypted at rest (DD P1) via set_mfa_secret; the plaintext is only
    used transiently here to build the provisioning URI.
    """
    import pyotp
    secret = user.get_mfa_secret()
    if not secret:
        secret = pyotp.random_base32()
        user.set_mfa_secret(secret)
        user.save(update_fields=['mfa_secret'])
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name='CyberTrust KSA')


def verify_totp(user, code):
    """Validate a 6-digit TOTP code against the user's secret."""
    import pyotp
    secret = user.get_mfa_secret()
    if not secret:
        return False
    return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)
