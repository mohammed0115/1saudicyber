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


# ---------- Auditor registration / onboarding ----------
@require_http_methods(["GET", "POST"])
def register(request):
    """Self-service auditor registration -> User + AuditorProfile(pending_review)."""
    if request.user.is_authenticated and services.get_auditor_profile(request.user):
        return redirect('auditors:onboarding')
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
            login(request, user)
            messages.success(request, 'تم استلام طلب تسجيلك كمدقّق. الحساب قيد مراجعة المنصّة.')
            return redirect('auditors:onboarding')
        return render(request, 'auditors/register.html', {'form': form})
    return render(request, 'auditors/register.html', {'form': AuditorRegistrationForm()})


@login_required
def onboarding(request):
    """Auditor onboarding/status page (own profile only)."""
    profile = services.get_auditor_profile(request.user)
    if profile is None:
        return redirect('auditors:register')
    return render(request, 'auditors/onboarding.html', {'profile': profile})


@login_required
def dashboard(request):
    """Auditor dashboard. Pending/suspended/inactive -> no company data."""
    profile = services.get_auditor_profile(request.user)
    if profile is None:
        return redirect('auditors:register')
    assignments = services.assignments_for_user(request.user) if profile.is_active_auditor() else None
    return render(request, 'auditors/dashboard.html', {
        'profile': profile, 'assignments': assignments})


@login_required
def assignment_detail(request, assignment_id):
    """Assignment detail for the owning auditor only. Context read-only when accepted+active."""
    assignment = services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    profile = assignment.auditor
    if not profile.is_active_auditor():
        # Pending/suspended/inactive auditor: no company data at all.
        return render(request, 'auditors/assignment_detail.html', {
            'assignment': assignment, 'profile': profile, 'context': None})

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
        'assignment': assignment, 'profile': profile, 'context': context})


@login_required
@require_http_methods(["POST"])
def assignment_respond(request, assignment_id):
    """Auditor accepts/rejects a 'requested' assignment (own assignment only)."""
    assignment = services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    if not assignment.auditor.is_active_auditor():
        messages.error(request, 'حسابك كمدقّق قيد المراجعة ولا يمكنه اتخاذ إجراء بعد.')
        return redirect('auditors:dashboard')
    action = request.POST.get('action', '')
    if services.respond_to_assignment(assignment, action):
        messages.success(request, 'تم تحديث حالة الطلب.')
    return redirect('auditors:assignment_detail', assignment_id=assignment.id)


# ---------- Company-facing: list + assign ----------
@login_required
def auditors_list(request):
    """List available platform auditors for a subscribed company to assign."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    if not services.can_company_assign(company):
        return render(request, 'compliance/subscription_required.html',
                      {'company': company, 'mode': 'assign'})
    return render(request, 'auditors/list.html', {
        'company': company, 'auditors': services.list_available_auditors()})


@login_required
@require_http_methods(["POST"])
def assign(request, auditor_id):
    """Assign the current company's file to a platform auditor (subscription required)."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    if not services.can_company_assign(company):
        return render(request, 'compliance/subscription_required.html',
                      {'company': company, 'mode': 'assign'})
    auditor = AuditorProfile.objects.filter(id=auditor_id, status='active', is_available=True).first()
    if auditor is None:
        messages.error(request, 'المدقّق غير متاح للإسناد.')
        return redirect('auditors:list')
    scope = request.POST.get('scope', 'reports_only')
    if scope not in dict(AuditorAssignment.SCOPE_CHOICES):
        scope = 'reports_only'
    _, created = services.create_assignment(company, auditor, requested_by=request.user, scope=scope)
    messages.success(request, 'تم إرسال طلب الإسناد إلى المدقّق.' if created
                     else 'يوجد طلب إسناد فعّال لهذا المدقّق بالفعل.')
    return redirect('auditors:list')
