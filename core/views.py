"""
Core Views - Landing page, Registration, Authentication
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
from .models import Company, User
from .forms import CompanyRegistrationForm
from ai_engine.services import classify_company


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
                'sectors': Company.SECTOR_CHOICES,
                'sizes': Company.SIZE_CHOICES,
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
        messages.success(request, 'Company registered successfully! AI classification in progress.')
        return redirect('dashboard:main')

    return render(request, 'core/register.html', {
        'form': CompanyRegistrationForm(),
        'sectors': Company.SECTOR_CHOICES,
        'sizes': Company.SIZE_CHOICES,
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
            messages.error(request, 'Invalid credentials. Please try again.')
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
            messages.success(request, 'Multi-factor authentication enabled.')
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


def logout_view(request):
    """User logout."""
    logout(request)
    return redirect('core:landing')


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
