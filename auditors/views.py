"""Phase 4C — auditor onboarding/dashboard + company assignment views.

Tenant-safe. Assignment requires the company's active subscription. Assigned
auditors get read-only context only; ControlAssessment stays staff-only.
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from core.models import User
from .forms import AuditorRegistrationForm
from .models import AuditorProfile, AuditorAssignment
from . import services
from core.roles import company_portal_required, auditor_portal_required


# ---------- Auditor registration / onboarding ----------
@require_http_methods(["GET", "POST"])
def register(request):
    """Self-service auditor registration -> User + AuditorProfile(pending_review).

    Role separation: an already-authenticated non-auditor (e.g. a company user)
    must NOT be able to silently create a new auditor account and have the session
    switched to it. Such users are shown a clear choice page on both GET and POST,
    and no account is ever created for them here.
    """
    if request.user.is_authenticated:
        # Existing auditor -> their own onboarding/status page.
        if services.get_auditor_profile(request.user):
            return redirect('auditors:onboarding')
        # Authenticated non-auditor: block silent account creation + session switch.
        return render(request, 'auditors/register_blocked.html', {
            'current_email': request.user.email,
        })
    from .journey import build_auditor_journey
    if request.method == 'POST':
        form = AuditorRegistrationForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            user = User.objects.create_user(
                username=d['email'], email=d['email'], password=d['password'],
                first_name=d['full_name'][:30], role='auditor')
            AuditorProfile.objects.create(
                user=user, full_name=d['full_name'],
                organization_name=d.get('organization_name', ''),
                license_or_membership_no=d.get('license_or_membership_no', ''),
                specialization=d.get('specialization', ''), city=d.get('city', ''),
                bio=d.get('bio', ''), status='pending_review')
            # Notify platform admins (in-app) that an auditor is awaiting approval.
            try:
                from core.notify_services import notify_many
                from django.urls import reverse
                from core.models import User as _U
                notify_many(_U.objects.filter(is_staff=True),
                            'طلب تسجيل مدقّق جديد بانتظار الموافقة',
                            body=d['full_name'], url=reverse('platform_admin:auditor_list'),
                            kind='assignment')
            except Exception:
                pass
            login(request, user)
            # Phase 8D-3B-AUTH-A: email a 6-digit verification OTP (non-blocking).
            from core import otp_services as otp
            otp.issue_and_send(user)
            messages.success(request, 'تم استلام طلب تسجيلك كمدقّق. الحساب قيد مراجعة المنصّة. '
                                      'تحقّق من بريدك الإلكتروني للحصول على رمز التحقق · Check your email for the verification code.')
            return redirect('auditors:onboarding')
        return render(request, 'auditors/register.html', {
            'form': form, 'auditor_journey': build_auditor_journey(request.user)})
    return render(request, 'auditors/register.html', {
        'form': AuditorRegistrationForm(),
        'auditor_journey': build_auditor_journey(request.user)})


@login_required
@auditor_portal_required
def onboarding(request):
    """Auditor onboarding/status page (own profile only)."""
    from .journey import build_auditor_journey
    profile = services.get_auditor_profile(request.user)
    if profile is None:
        return redirect('auditors:register')
    from .badges import auditor_framework_badges
    return render(request, 'auditors/onboarding.html', {
        'profile': profile, 'framework_badges': auditor_framework_badges(profile),
        'auditor_journey': build_auditor_journey(request.user)})


@login_required
@auditor_portal_required
def dashboard(request):
    """Auditor dashboard. Pending/suspended/inactive -> no company data."""
    from .journey import build_auditor_journey
    profile = services.get_auditor_profile(request.user)
    if profile is None:
        return redirect('auditors:register')
    pending_requests = accepted_assignments = None
    if profile.is_active_auditor:
        assignments = services.assignments_for_user(request.user)
        pending_requests = assignments.filter(status='requested')
        accepted_assignments = assignments.filter(status='accepted')
    from .badges import auditor_framework_badges
    return render(request, 'auditors/dashboard.html', {
        'profile': profile, 'pending_requests': pending_requests,
        'accepted_assignments': accepted_assignments,
        'framework_badges': auditor_framework_badges(profile),
        'auditor_journey': build_auditor_journey(request.user)})


@login_required
@auditor_portal_required
def assignment_detail(request, assignment_id):
    """Assignment detail for the owning auditor only. Context read-only when accepted+active."""
    assignment = services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    from .journey import build_auditor_journey
    journey = build_auditor_journey(request.user)
    profile = assignment.auditor
    if not profile.is_active_auditor:
        # Pending/suspended/inactive auditor: no company data at all.
        return render(request, 'auditors/assignment_detail.html', {
            'assignment': assignment, 'profile': profile, 'context': None,
            'auditor_journey': journey})

    context = None
    if services.auditor_can_view_company_context(assignment):
        from compliance.reporting import (get_approved_framework_versions,
                                           build_executive_summary, build_evidence_matrix)
        from billing.subscription_access import company_has_active_subscription
        company = assignment.company
        context = {
            'company': company,
            'subscription_active': company_has_active_subscription(company),
            'frameworks': get_approved_framework_versions(company),
            'summary': build_executive_summary(company),
            'matrix_rows': build_evidence_matrix(company)[:50],
        }
    return render(request, 'auditors/assignment_detail.html', {
        'assignment': assignment, 'profile': profile, 'context': context,
        'auditor_journey': journey})


@login_required
@require_http_methods(["POST"])
@auditor_portal_required
def assignment_respond(request, assignment_id):
    """Auditor accepts/rejects a 'requested' assignment (own assignment only)."""
    assignment = services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    if not assignment.auditor.is_active_auditor:
        messages.error(request, 'حسابك كمدقّق قيد المراجعة ولا يمكنه اتخاذ إجراء بعد.')
        return redirect('auditors:dashboard')
    action = request.POST.get('action', '')
    note = request.POST.get('reason', '')
    ok, err = services.respond_to_assignment(assignment, action, note=note, responder=request.user)
    if ok:
        messages.success(request, 'تم قبول طلب المراجعة.' if action == 'accept' else 'تم رفض الطلب.')
    else:
        messages.error(request, err)
    return redirect('auditors:assignment_detail', assignment_id=assignment.id)


@login_required
@require_http_methods(["POST"])
@company_portal_required
def cancel_assignment(request, assignment_id):
    """Company cancels its OWN pending (requested) review request. Tenant-scoped."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    a = AuditorAssignment.objects.filter(id=assignment_id, company=company).first()
    if a is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّ شركتك.')
    elif services.cancel_assignment(a, by=request.user):
        messages.success(request, 'تم إلغاء طلب المراجعة.')
    else:
        messages.error(request, 'لا يمكن إلغاء هذا الطلب في حالته الحالية.')
    return redirect('auditors:list')


# ---------- Company-facing: list + assign ----------
@login_required
@company_portal_required
def auditors_list(request):
    """List available platform auditors for a subscribed company to assign."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    if not services.can_company_assign(company):
        return render(request, 'compliance/subscription_required.html',
                      {'company': company, 'mode': 'assign'})
    from compliance.workflow_stepper import build_company_workflow_stepper
    # Current request state drives the UI: a company may only have one active assignment.
    current = services.company_active_assignment(company)
    last_rejected = None
    if current is None:
        last_rejected = (AuditorAssignment.objects.filter(company=company, status='rejected')
                         .select_related('auditor').order_by('-responded_at').first())
    return render(request, 'auditors/list.html', {
        'company': company, 'auditors': services.list_available_auditors(),
        'current_assignment': current, 'last_rejected': last_rejected,
        'stepper': build_company_workflow_stepper(company)})


@login_required
@require_http_methods(["POST"])
@company_portal_required
def assign(request, auditor_id):
    """Assign the current company's file to a platform auditor (subscription required)."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    if not services.can_company_assign(company):
        return render(request, 'compliance/subscription_required.html',
                      {'company': company, 'mode': 'assign'})
    # Plan gate: auditor review must be enabled on the plan (permissive when no plan).
    from billing.access import enforce_feature
    result, blocked = enforce_feature(request, company, 'auditor_review')
    if blocked:
        return render(request, 'billing/feature_blocked.html', {
            'company': company, 'access': result,
            'feature_title': 'مراجعة المدقّق · Auditor review'})
    auditor = AuditorProfile.objects.filter(id=auditor_id, status='active', is_available=True).first()
    if auditor is None:
        messages.error(request, 'المدقّق غير متاح للإسناد.')
        return redirect('auditors:list')
    scope = request.POST.get('scope', 'reports_only')
    if scope not in dict(AuditorAssignment.SCOPE_CHOICES):
        scope = 'reports_only'
    _, created = services.create_assignment(company, auditor, requested_by=request.user,
                                            scope=scope, notes=request.POST.get('note', ''))
    messages.success(request, 'تم إرسال طلب المراجعة إلى المدقق، بانتظار الموافقة.' if created
                     else 'لديك طلب مراجعة فعّال بالفعل. ألغِ الطلب الحالي قبل اختيار مدقق آخر.')
    return redirect('auditors:list')
