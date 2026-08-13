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
    """Generate (and persist if needed) a TOTP secret and return the otpauth URI for a QR code."""
    import pyotp
    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        user.save(update_fields=['mfa_secret'])
    return pyotp.totp.TOTP(user.mfa_secret).provisioning_uri(
        name=user.email, issuer_name='CyberTrust KSA')


def verify_totp(user, code):
    """Validate a 6-digit TOTP code against the user's secret."""
    import pyotp
    if not user.mfa_secret:
        return False
    return pyotp.TOTP(user.mfa_secret).verify(str(code).strip(), valid_window=1)


FRAMEWORK_RULES_VERSION = '2026.08'


def recommend_frameworks(answers):
    """Return deterministic framework recommendations and auditable rule reasons.

    The recommendation is intentionally rule-based rather than model-generated: a
    company's declared regulatory/customer scope is the authoritative onboarding
    signal, and every result must be explainable later.
    """
    normalized = {
        'nca_scope': bool(answers.get('nca_scope')),
        'aramco_supplier': bool(answers.get('aramco_supplier')),
        'sabic_supplier': bool(answers.get('sabic_supplier')),
    }
    rules = (
        ('NCA_ECC', 'nca_scope', 'The company declared NCA/government or critical-infrastructure scope.'),
        ('ARAMCO_SACS002', 'aramco_supplier', 'The company declared that it supplies or contracts with Aramco.'),
        ('SABIC_CT', 'sabic_supplier', 'The company declared that it supplies or contracts with SABIC.'),
    )
    codes = []
    rationale = {}
    for framework_code, answer_key, reason in rules:
        if normalized[answer_key]:
            codes.append(framework_code)
            rationale[framework_code] = {
                'rule_id': f'{FRAMEWORK_RULES_VERSION}:{answer_key}',
                'answer_key': answer_key,
                'reason': reason,
            }

    if not codes:
        raise ValueError('At least one framework-scope question must be answered yes.')
    return {
        'answers': normalized,
        'framework_codes': codes,
        'rationale': rationale,
        'rules_version': FRAMEWORK_RULES_VERSION,
    }


def record_framework_decision(company, user, recommendation):
    """Persist the onboarding decision so it can be reconstructed and audited."""
    from core.models import FrameworkDecision

    return FrameworkDecision.objects.create(
        company=company,
        decided_by=user,
        answers=recommendation['answers'],
        recommended_framework_codes=recommendation['framework_codes'],
        rationale=recommendation['rationale'],
        rules_version=recommendation['rules_version'],
    )
