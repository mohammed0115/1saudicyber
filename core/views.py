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
    from django.conf import settings
    from django.core.cache import cache
    # DD-fix (perf): the official control catalog (~417 rows) changes only on import;
    # cache the count so the public landing page doesn't COUNT on every anonymous hit.
    # Skipped under TESTING so the shared locmem cache never pollutes test isolation.
    controls_monitored = None if getattr(settings, 'TESTING', False) else cache.get('official_controls_count')
    if controls_monitored is None:
        controls_monitored = Control.objects.count()
        if not getattr(settings, 'TESTING', False):
            cache.set('official_controls_count', controls_monitored, 3600)
    stats = {
        'companies_registered': Company.objects.count(),
        'assessments_completed': 0,
        'controls_monitored': controls_monitored,
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
    """Standalone company registration - no external API verification.

    Phase 8D-3C: anonymous-only — never create/switch account context over an
    existing authenticated session.
    """
    if request.user.is_authenticated:
        from .roles import portal_for
        return render(request, 'core/already_authenticated.html',
                      {'portal': portal_for(request.user)})
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
        from core import login_throttle
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        # DD-fix: brute-force lockout on the HTML login form.
        if login_throttle.is_locked(username, request):
            return render(request, 'core/login.html', {
                'login_error': _('تم إيقاف المحاولات مؤقتًا بسبب تكرار الفشل. حاول لاحقًا.'),
                'email': username,
            })
        user = authenticate(request, username=username, password=password)
        if user:
            login_throttle.clear(username, request)
            if getattr(user, 'mfa_enabled', False):
                request.session['mfa_pending_user'] = user.id
                request.session['mfa_next'] = request.GET.get('next', '/dashboard/')
                return redirect('core:mfa_challenge')
            login(request, user)
            next_url = request.GET.get('next', '/dashboard/')
            return redirect(next_url)
        login_throttle.record_failure(username, request)
        # PILOT-HOTFIX-B (C): surface the failure INLINE on /login/ via template
        # context — NOT via global django messages, which persist in the session and
        # leaked onto unrelated pages (password reset / platform-admin / get-started).
        # Preserve the email for convenience; never echo the password back.
        return render(request, 'core/login.html', {
            'login_error': _('بيانات الدخول غير صحيحة. حاول مرة أخرى.'),
            'email': username,
        })
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
        messages.error(request, 'رمز المصادقة غير صحيح.')
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
        messages.error(request, 'الرمز غير صحيح. أعد المسح وحاول مرة أخرى.')
    uri = mfa_provisioning_uri(request.user)
    # Show the plaintext secret (decrypted) for manual authenticator entry — the stored
    # field is ciphertext (DD P1).
    return render(request, 'core/mfa_setup.html',
                  {'provisioning_uri': uri, 'secret': request.user.get_mfa_secret()})


def verify_email(request, token):
    """FR-002.8: confirm a user's email via the one-time token."""
    from core.models import EmailVerificationToken
    try:
        vt = EmailVerificationToken.objects.select_related('user').get(token=token, used=False)
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'رابط التحقق غير صالح أو استُخدم من قبل.')
        return redirect('core:login')
    vt.used = True
    vt.save(update_fields=['used'])
    vt.user.email_verified = True
    vt.user.save(update_fields=['email_verified'])
    messages.success(request, 'تم توثيق بريدك الإلكتروني بنجاح.')
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
    from auditors.models import AuditorProfile
    user = request.user
    # Auditors have no company; after verifying, route them to their own dashboard.
    dest = 'auditors:dashboard' if AuditorProfile.objects.filter(user=user).exists() else 'dashboard:main'
    if user.email_verified:
        messages.info(request, 'بريدك الإلكتروني مُوثّق بالفعل.')
        return redirect(dest)

    if request.method == 'POST':
        ok, reason = otp.verify_otp(user, request.POST.get('code', ''))
        if ok:
            messages.success(request, 'تم توثيق بريدك الإلكتروني بنجاح.')
            return redirect(dest)
        msgs = {
            'no_otp': 'لا يوجد رمز نشِط. اطلب رمزًا جديدًا.',
            'expired': 'انتهت صلاحية الرمز. اطلب رمزًا جديدًا.',
            'too_many_attempts': 'تم تجاوز عدد المحاولات المسموح بها. اطلب رمزًا جديدًا.',
            'invalid': 'الرمز غير صحيح. حاول مرة أخرى.',
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
        messages.success(request, 'تم إرسال رمز تحقق جديد إلى بريدك.')
    else:
        messages.info(request, 'يرجى الانتظار قليلًا قبل طلب رمز جديد.')
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
    # Phase 8D-3C: anonymous-only — an already-authenticated user (company, auditor
    # or staff) must not silently create/switch into a new company session.
    if request.user.is_authenticated:
        from .roles import portal_for, get_user_company
        # A company user who already has a company just returns to their onboarding;
        # everyone else (auditor, staff, or an account with no company) is blocked
        # from creating/switching into a brand-new company session.
        if get_user_company(request.user) is not None:
            return redirect('core:onboarding')
        return render(request, 'core/already_authenticated.html',
                      {'portal': portal_for(request.user)})
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
                                      'للحصول على رمز التحقق.')
            return redirect('core:onboarding')
        # PILOT-HOTFIX-B (F): on validation error, keep the user on the step that
        # actually failed (default: the last step, where the submit + non-field
        # errors live) instead of collapsing every step onto one long page.
        return render(request, 'onboarding/register.html',
                      {'form': form, 'error_step': _wizard_error_step(form)})
    return render(request, 'onboarding/register.html', {'form': SelfServiceRegistrationForm()})


# Which registration-wizard step each field belongs to (mirrors onboarding/register.html).
_WIZARD_STEP_FIELDS = {
    0: ('first_name', 'last_name', 'email', 'phone', 'password', 'password_confirm'),
    1: ('company_name_ar', 'company_name', 'cr_number', 'sector', 'size', 'city',
        'country', 'description'),
    2: ('target_nca', 'target_aramco', 'target_sabic', 'accept_terms'),
}


def _wizard_error_step(form):
    """Index (0-2) of the first wizard step with a field error; non-field errors -> last step."""
    for step in (0, 1, 2):
        if any(name in form.errors for name in _WIZARD_STEP_FIELDS[step]):
            return step
    return 2


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
@require_http_methods(["POST"])
def resend_verification_link(request):
    """Resend the email-verification LINK from the onboarding page. Reuses the existing
    core.services.send_verification_email — no new verification system. POST + CSRF + login only.
    Never reveals whether the email exists/verified; always shows the same success message.
    """
    user = request.user
    if not user.email_verified and user.email:
        try:
            from core.services import send_verification_email
            send_verification_email(user)
        except Exception:
            pass
    messages.success(request, 'تم إرسال رابط التحقق مرة أخرى، يرجى مراجعة بريدك الإلكتروني.')
    return redirect('core:onboarding')


@login_required
@require_http_methods(["GET", "POST"])
def delete_company_data(request):
    """
    PDPL right-to-deletion (NFR-048): a company admin may permanently delete
    their company and all associated data. Requires explicit typed confirmation.
    """
    if request.user.role not in ('company_admin', 'admin'):
        messages.error(request, 'حذف البيانات متاح لمسؤول الشركة فقط.')
        return redirect('dashboard:main')
    company = request.user.company
    if request.method == 'POST':
        confirm = request.POST.get('confirm', '').strip().upper()
        if not company or confirm != 'DELETE':
            messages.error(request, 'اكتب DELETE للتأكيد.')
            return render(request, 'core/delete_company.html', {'company': company})
        # P0-02: a company with a final audit record (issued report) must be retained — deleting
        # it would cascade the immutable report away. Refuse BEFORE logging out / deleting.
        from core.models import CompanyDeletionProtected
        try:
            name = company.name
            company.delete()  # cascades to controls, evidence, scores, alerts, users
        except CompanyDeletionProtected:
            messages.error(request, 'لا يمكن حذف الشركة لوجود تقرير تدقيق نهائي صادر يجب الاحتفاظ به. '
                                    'يرجى التواصل مع الدعم للأرشفة بدلًا من الحذف.')
            return render(request, 'core/delete_company.html', {'company': company})
        logout(request)
        messages.success(request, f'تم حذف جميع بيانات «{name}» نهائيًا.')
        return redirect('core:landing')
    return render(request, 'core/delete_company.html', {'company': company})


# ============================================================
# DD-fix (commercial) — team invites / user management
# ============================================================
@login_required
def team_view(request):
    """Company admins manage their team: list members + pending invites, send new invites."""
    from .models import UserInvite
    from .invite_services import create_invite, INVITABLE_ROLES
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    can_invite = request.user.role in ('company_admin', 'admin') or request.user.is_staff
    if request.method == 'POST':
        if not can_invite:
            messages.error(request, 'لا تملك صلاحية دعوة أعضاء.')
            return redirect('core:team')
        try:
            create_invite(company, request.POST.get('email', ''),
                          request.POST.get('role', 'compliance_officer'), request.user)
            messages.success(request, 'تم إرسال الدعوة.')
        except ValueError as e:
            messages.error(request, 'تعذّر إرسال الدعوة: %s' % (
                'البريد مستخدم بالفعل' if 'already exists' in str(e) else 'تحقّق من البريد'))
        return redirect('core:team')
    return render(request, 'core/team.html', {
        'members': company.users.order_by('role', 'email'),
        'invites': UserInvite.objects.filter(company=company, status='pending'),
        'can_invite': can_invite,
        'invitable_roles': INVITABLE_ROLES,
    })


def accept_invite_view(request, token):
    """Public accept-invite page: set name + password to join the company."""
    from .models import UserInvite
    from .invite_services import accept_invite
    invite = UserInvite.objects.filter(token=token).first()
    if invite is None or not invite.is_valid():
        return render(request, 'core/invite_invalid.html', status=404)
    if request.method == 'POST':
        pwd = request.POST.get('password', '')
        if len(pwd) < 12:
            return render(request, 'core/accept_invite.html',
                          {'invite': invite, 'error': 'كلمة المرور يجب ألا تقل عن 12 حرفًا.'})
        try:
            user = accept_invite(invite, first_name=request.POST.get('first_name', ''),
                                 last_name=request.POST.get('last_name', ''), password=pwd)
        except ValueError:
            return render(request, 'core/invite_invalid.html', status=404)
        login(request, user)
        return redirect('/dashboard/')
    return render(request, 'core/accept_invite.html', {'invite': invite})


@login_required
def notifications_inbox(request):
    """In-app notification inbox for the current user. Marks all as read on view."""
    from .models import Notification
    notes = list(Notification.objects.filter(recipient=request.user)[:100])
    # Mark unread as read (viewing the inbox clears the badge).
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return render(request, 'core/notifications.html', {'notes': notes})


@login_required
@require_http_methods(["POST"])
def notification_open(request, note_id):
    """Mark one notification read and redirect to its target url (or the inbox)."""
    from .models import Notification
    n = Notification.objects.filter(id=note_id, recipient=request.user).first()
    if n:
        if not n.is_read:
            n.is_read = True
            n.save(update_fields=['is_read'])
        if n.url:
            return redirect(n.url)
    return redirect('core:notifications_inbox')


@login_required
def settings_hub(request):
    """Unified company settings hub — profile summary + links to security (MFA),
    team management, and data deletion. Read-only overview; each action lives on
    its own audited page. Company users only.
    """
    company = getattr(request.user, 'company', None)
    if company is None:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'core/settings.html', {
        'company': company,
        'mfa_enabled': getattr(request.user, 'mfa_enabled', False),
        'is_company_admin': request.user.role == 'company_admin',
    })
