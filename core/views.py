"""
Core Views - Landing page, Registration, Authentication
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from .models import Company, User
from .forms import CompanyRegistrationForm
from .forms import SECTOR_CHOICES_AR as _SECTOR_AR, SIZE_CHOICES_AR as _SIZE_AR
from ai_engine.services import classify_company


def privacy_policy(request):
    """Phase 8D-2-FIX-A — public privacy policy page (Arabic-first, no login)."""
    return render(request, 'core/privacy.html')


def terms_of_use(request):
    """Phase 8D-2-FIX-A — public terms of use page (Arabic-first, no login)."""
    return render(request, 'core/terms.html')


def landing_page(request):
    """Phase 0: Landing page with platform overview."""
    from compliance.models import Control
    stats = {
        'companies_registered': Company.objects.count(),
        'assessments_completed': 0,
        'controls_monitored': Control.objects.count(),
        'faster_assessments': 75,
        'cost_reduction': 60,
    }
    return render(request, 'core/landing.html', {'stats': stats})


def _create_company_control_checklist(company):
    """UC-001 step 9 / FR-003: build the company-specific control set from targeted frameworks."""
    from compliance.models import Control, CompanyControl
    fw_codes = []
    if company.target_nca:
        fw_codes.append('NCA_ECC')
    if company.target_aramco:
        fw_codes.append('ARAMCO_SACS002')
    if company.target_sabic:
        fw_codes.append('SABIC_CT')
    if not fw_codes:
        return 0
    controls = Control.objects.filter(framework__code__in=fw_codes)
    rows = [CompanyControl(company=company, control=c) for c in controls]
    CompanyControl.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


@require_http_methods(["GET", "POST"])
def register_company(request):
    """Standalone company registration - no external API verification."""
    if request.method == 'POST':
        form = CompanyRegistrationForm(request.POST)
        if not form.is_valid():
            # FR-002.10/.11 and password policy errors are surfaced here.
            return render(request, 'core/register.html', {
                'form': form,
                'sectors': _SECTOR_AR,
                'sizes': _SIZE_AR,
            })

        data = form.cleaned_data
        with transaction.atomic():
            company = Company.objects.create(
                name=data['company_name'],
                name_ar=data.get('company_name_ar', ''),
                cr_number=data['cr_number'],
                sector=data['sector'],
                size=data['size'],
                contact_email=data['email'],
                contact_phone=data.get('phone', ''),
                city=data.get('city', ''),
                target_aramco=data.get('target_aramco', False),
                target_sabic=data.get('target_sabic', False),
                target_nca=data.get('target_nca', False),
            )
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                company=company,
                role='company_admin',
            )

        # Run AI Classification (best-effort; failure must not block registration)
        try:
            classification = classify_company({
                'name': company.name,
                'sector': company.get_sector_display(),
                'size': company.get_size_display(),
                'target_aramco': company.target_aramco,
                'target_sabic': company.target_sabic,
                'target_nca': company.target_nca,
            })
            if 'error' not in classification:
                from django.utils import timezone
                company.risk_level = classification.get('risk_level', 'medium')
                company.classification_summary = classification.get('summary_en', '')
                company.classification_summary_ar = classification.get('summary_ar', '')
                company.classification_date = timezone.now()
                company.status = 'classified'
                company.save()
        except Exception:
            pass

        # UC-001 step 9: create the company's control checklist regardless of AI status.
        _create_company_control_checklist(company)

        # FR-002.8: send email verification (does not block login in dev).
        from core.services import send_verification_email
        send_verification_email(user)

        login(request, user)
        messages.success(request, _('تم تسجيل الشركة بنجاح. جارٍ تجهيز التصنيف الأولي.'))
        return redirect('dashboard:main')

    return render(request, 'core/register.html', {
        'form': CompanyRegistrationForm(),
        'sectors': _SECTOR_AR,
        'sizes': _SIZE_AR,
    })


@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login. If MFA is enabled, defer to a TOTP challenge before completing login."""
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            if getattr(user, 'mfa_enabled', False):
                request.session['mfa_pending_user'] = user.id
                request.session['mfa_next'] = request.GET.get('next', '/dashboard/')
                return redirect('core:mfa_challenge')
            login(request, user)
            next_url = request.GET.get('next', '/dashboard/')
            return redirect(next_url)
        else:
            messages.error(request, _('بيانات الدخول غير صحيحة. حاول مرة أخرى.'))
    return render(request, 'core/login.html')


@require_http_methods(["GET", "POST"])
def mfa_challenge(request):
    """Second factor: verify the TOTP code for a user who passed password auth."""
    user_id = request.session.get('mfa_pending_user')
    if not user_id:
        return redirect('core:login')
    if request.method == 'POST':
        from core.services import verify_totp
        user = User.objects.get(id=user_id)
        if verify_totp(user, request.POST.get('code', '')):
            login(request, user)
            next_url = request.session.pop('mfa_next', '/dashboard/')
            request.session.pop('mfa_pending_user', None)
            return redirect(next_url)
        messages.error(request, 'Invalid authentication code.')
    return render(request, 'core/mfa_challenge.html')


@login_required
@require_http_methods(["GET", "POST"])
def mfa_setup(request):
    """Enroll the current user in TOTP MFA (FR-012.3)."""
    from core.services import mfa_provisioning_uri, verify_totp
    if request.method == 'POST':
        if verify_totp(request.user, request.POST.get('code', '')):
            request.user.mfa_enabled = True
            request.user.save(update_fields=['mfa_enabled'])
            messages.success(request, _('تم تفعيل التحقق بخطوتين.'))
            return redirect('dashboard:main')
        messages.error(request, 'Invalid code. Please re-scan and try again.')
    uri = mfa_provisioning_uri(request.user)
    return render(request, 'core/mfa_setup.html', {'provisioning_uri': uri, 'secret': request.user.mfa_secret})


def verify_email(request, token):
    """FR-002.8: confirm a user's email via the one-time token."""
    from core.models import EmailVerificationToken
    try:
        vt = EmailVerificationToken.objects.select_related('user').get(token=token, used=False)
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'This verification link is invalid or already used.')
        return redirect('core:login')
    vt.used = True
    vt.save(update_fields=['used'])
    vt.user.email_verified = True
    vt.user.save(update_fields=['email_verified'])
    messages.success(request, 'Email verified successfully.')
    return redirect('dashboard:main' if request.user.is_authenticated else 'core:login')


# ============================================================
# Phase 8D-3B-AUTH-A — 6-digit email OTP verification (non-blocking).
# Does NOT gate login (existing/legacy users keep working); it is a guided
# post-registration step to confirm email ownership.
# ============================================================
@login_required
@require_http_methods(["GET", "POST"])
def verify_email_otp(request):
    """Enter the 6-digit OTP emailed at registration to mark email verified."""
    from . import otp_services as otp
    user = request.user
    if user.email_verified:
        messages.info(request, 'بريدك الإلكتروني مُوثّق بالفعل · Your email is already verified.')
        return redirect('dashboard:main')

    if request.method == 'POST':
        ok, reason = otp.verify_otp(user, request.POST.get('code', ''))
        if ok:
            messages.success(request, 'تم توثيق بريدك الإلكتروني بنجاح · Email verified successfully.')
            return redirect('dashboard:main')
        msgs = {
            'no_otp': 'لا يوجد رمز نشِط. اطلب رمزًا جديدًا · No active code. Please request a new one.',
            'expired': 'انتهت صلاحية الرمز. اطلب رمزًا جديدًا · The code has expired. Request a new one.',
            'too_many_attempts': 'تم تجاوز عدد المحاولات المسموح بها. اطلب رمزًا جديدًا · Too many attempts. Request a new code.',
            'invalid': 'الرمز غير صحيح. حاول مرة أخرى · Invalid code. Please try again.',
        }
        messages.error(request, msgs.get(reason, msgs['invalid']))
        return render(request, 'core/verify_email_otp.html', {'email': user.email})

    return render(request, 'core/verify_email_otp.html', {'email': user.email})


@login_required
@require_http_methods(["POST"])
def resend_email_otp(request):
    """Resend a fresh OTP (throttled). Never reveals the code in the response."""
    from . import otp_services as otp
    user = request.user
    if user.email_verified:
        return redirect('dashboard:main')
    if otp.can_resend(user):
        otp.issue_and_send(user)
        messages.success(request, 'تم إرسال رمز تحقق جديد إلى بريدك · A new verification code has been sent to your email.')
    else:
        messages.info(request, 'يرجى الانتظار قبل طلب رمز جديد · Please wait a moment before requesting a new code.')
    return redirect('core:verify_email_otp')


def logout_view(request):
    """User logout. Honors a safe internal ?next= (e.g. log out then register as auditor)."""
    from django.utils.http import url_has_allowed_host_and_scheme
    next_url = request.GET.get('next', '')
    logout(request)
    if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('core:landing')


# ============================================================
# Phase 4A — Self-service company registration + onboarding (additive).
# Does NOT replace register_company; never creates CompanyControl; tenant-safe.
# ============================================================
def get_started(request):
    """Entry experience: choose 'company' or 'auditor'. Read-only, public."""
    return render(request, 'onboarding/start.html')


def auditor_interest(request):
    """Auditor onboarding placeholder (no auditor workflow in Phase 4A)."""
    return render(request, 'onboarding/auditor.html')


@require_http_methods(["GET", "POST"])
def company_self_register(request):
    """Self-service company registration → creates User + Company, logs in,
    routes to onboarding. Additive; no CompanyControl, no destructive change."""
    from .forms import SelfServiceRegistrationForm
    if request.user.is_authenticated:
        return redirect('core:onboarding')
    if request.method == 'POST':
        form = SelfServiceRegistrationForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            with transaction.atomic():
                company = Company.objects.create(
                    name=d.get('company_name') or d['company_name_ar'],
                    name_ar=d['company_name_ar'],
                    cr_number=d['cr_number'],
                    sector=d['sector'],
                    size=d['size'],
                    city=d.get('city', ''),
                    country=d.get('country') or 'SA',
                    description=d.get('description', ''),
                    contact_email=d['email'],
                    contact_phone=d.get('phone', ''),
                    target_nca=d.get('target_nca', False),
                    target_aramco=d.get('target_aramco', False),
                    target_sabic=d.get('target_sabic', False),
                )
                user = User.objects.create_user(
                    username=d['email'], email=d['email'], password=d['password'],
                    first_name=d['first_name'], last_name=d['last_name'],
                    phone=d.get('phone', ''), company=company, role='company_admin',
                )
            login(request, user)
            # Phase 8D-3B-AUTH-A: issue + email a 6-digit verification OTP (non-blocking).
            from . import otp_services as otp
            otp.issue_and_send(user)
            messages.success(request, 'تم إنشاء حساب شركتك بنجاح. تحقّق من بريدك الإلكتروني '
                                      'للحصول على رمز التحقق · Check your email for the verification code.')
            return redirect('core:onboarding')
        return render(request, 'onboarding/register.html', {'form': form})
    return render(request, 'onboarding/register.html', {'form': SelfServiceRegistrationForm()})


@login_required
def onboarding(request):
    """Welcome + onboarding steps for the user's own company (tenant-scoped)."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'onboarding/welcome.html', {'company': company})


@login_required
@require_http_methods(["POST"])
def onboarding_complete(request):
    """Mark onboarding complete for the user's own company, then enter the journey."""
    company = request.user.company
    if company and not company.onboarding_completed:
        company.onboarding_completed = True
        company.save(update_fields=['onboarding_completed', 'updated_at'])
    messages.success(request, 'تم إكمال التهيئة. هذه لوحة رحلة الامتثال الخاصة بك.')
    return redirect('compliance:dashboard')


@login_required
@require_http_methods(["GET", "POST"])
def delete_company_data(request):
    """
    PDPL right-to-deletion (NFR-048): a company admin may permanently delete
    their company and all associated data. Requires explicit typed confirmation.
    """
    if request.user.role not in ('company_admin', 'admin'):
        messages.error(request, 'Only a company administrator can request data deletion.')
        return redirect('dashboard:main')
    company = request.user.company
    if request.method == 'POST':
        confirm = request.POST.get('confirm', '').strip().upper()
        if not company or confirm != 'DELETE':
            messages.error(request, 'Type DELETE to confirm.')
            return render(request, 'core/delete_company.html', {'company': company})
        name = company.name
        logout(request)
        company.delete()  # cascades to controls, evidence, scores, alerts, users
        messages.success(request, f'All data for {name} has been permanently deleted.')
        return redirect('core:landing')
    return render(request, 'core/delete_company.html', {'company': company})
