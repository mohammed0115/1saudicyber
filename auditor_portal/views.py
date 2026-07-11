"""
Auditor Portal Views — internal human review of a company's controls/evidence.

INTERNAL review only. This portal NEVER issues an official certification or
accreditation and never marks a company "certified" — that would contradict the
platform's stated positioning. It records auditor notes, document requests, and a
final internal audit report. Access + object scoping are enforced per auditor.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from compliance.models import Assessment, CompanyControl, Evidence
from .models import AuditorNote, DocumentRequest, AuditReport


def _active_auditor_profile(user):
    """Return the user's AuditorProfile only if it is an ACTIVE auditor, else None."""
    if not getattr(user, 'is_authenticated', False):
        return None
    from auditors.services import get_auditor_profile
    p = get_auditor_profile(user)
    # is_active_auditor is a @property — evaluate it directly (never a bound method).
    return p if (p is not None and p.is_active_auditor) else None


def auditor_required(view_func):
    """Only staff/superuser or an ACTIVE auditor may use the auditor portal.

    (Was: any user whose role == 'auditor', which let pending/suspended auditors in.)
    """
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser
                or _active_auditor_profile(request.user) is not None):
            messages.error(request, 'Access denied. An active auditor account is required.')
            return redirect('dashboard:main')
        return view_func(request, *args, **kwargs)
    return wrapper


def ensure_assessments_for_auditor(user):
    """Idempotently create an internal Assessment for each ACCEPTED auditor assignment.

    Wires the portal to the existing auditors.AuditorAssignment flow so an assigned,
    active auditor sees the company's controls for review. Never issues certificates.
    """
    profile = _active_auditor_profile(user)
    if profile is None:
        return
    from auditors.models import AuditorAssignment
    for asg in (AuditorAssignment.objects.filter(auditor=profile, status='accepted')
                .select_related('company')):
        Assessment.objects.get_or_create(
            company=asg.company, assigned_auditor=user,
            defaults=dict(assessment_type='formal_audit', status='auditor_review',
                          started_at=timezone.now()),
        )


@login_required
@auditor_required
def auditor_dashboard(request):
    """Auditor main dashboard — assessments from the auditor's accepted assignments."""
    ensure_assessments_for_auditor(request.user)
    assessments = (Assessment.objects.filter(assigned_auditor=request.user)
                   .select_related('company').order_by('-created_at'))
    context = {
        'assessments': assessments,
        'pending': assessments.filter(status='auditor_review').count(),
        'completed': assessments.filter(status='completed').count(),
    }
    return render(request, 'auditor_portal/dashboard.html', context)


@login_required
@auditor_required
def review_assessment(request, assessment_id):
    """Review a specific assessment — view all controls and evidence (own assignment only)."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_controls = (CompanyControl.objects.filter(company=assessment.company)
                        .select_related('control', 'control__framework', 'control__domain')
                        .order_by('control__domain__order', 'control__control_id'))
    from .workspace import review_workspace_summary
    context = {
        'assessment': assessment,
        'company_controls': company_controls,
        'notes': AuditorNote.objects.filter(assessment=assessment),
        'document_requests': DocumentRequest.objects.filter(assessment=assessment),
        'workspace': review_workspace_summary(assessment),
    }
    return render(request, 'auditor_portal/review_assessment.html', context)


@login_required
@auditor_required
def review_control(request, assessment_id, control_id):
    """Review a specific control's evidence (own assignment + own company only)."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    evidences = Evidence.objects.filter(company_control=company_control).order_by('-uploaded_at')
    context = {
        'assessment': assessment,
        'company_control': company_control,
        'evidences': evidences,
        'notes': AuditorNote.objects.filter(assessment=assessment, company_control=company_control),
        'document_requests': DocumentRequest.objects.filter(
            assessment=assessment, company_control=company_control),
    }
    return render(request, 'auditor_portal/review_control.html', context)


@login_required
@auditor_required
def add_note(request, assessment_id, control_id):
    """Add an auditor note to a control (POST-only; tenant-scoped to the assessment)."""
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
        # SECURITY: scope the control to THIS assessment's company (was: id only -> cross-tenant).
        company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
        AuditorNote.objects.create(
            assessment=assessment, company_control=company_control, auditor=request.user,
            note=request.POST.get('note', ''),
            is_finding=request.POST.get('is_finding') == 'on',
            requires_action=request.POST.get('requires_action') == 'on',
        )
        messages.success(request, 'تمت إضافة ملاحظة المدقق.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
def request_document(request, assessment_id, control_id):
    """Request an additional document (POST-only; tenant-scoped to the assessment)."""
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
        company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
        # Reason/description is required so the company knows what to provide.
        desc = (request.POST.get('description', '') or '').strip()
        desc_ar = (request.POST.get('description_ar', '') or '').strip()
        if not desc and not desc_ar:
            messages.error(request, 'سبب/وصف الطلب مطلوب لإرسال طلب استكمال.')
        else:
            DocumentRequest.objects.create(
                assessment=assessment, company_control=company_control, auditor=request.user,
                description=desc, description_ar=desc_ar)
            messages.success(request, 'تم إرسال طلب الاستكمال إلى الشركة.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
def submit_report(request, assessment_id):
    """Submit the final INTERNAL audit report (POST-only; own assignment only).

    Records the internal report and closes the assessment. It does NOT issue any
    certificate and NEVER marks the company "certified" — this is an internal
    readiness review, not an official certification/accreditation.
    """
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
        AuditReport.objects.update_or_create(
            assessment=assessment,
            defaults=dict(auditor=request.user, verdict=request.POST.get('verdict', 'fail'),
                          executive_summary=request.POST.get('executive_summary', ''),
                          executive_summary_ar=request.POST.get('executive_summary_ar', '')),
        )
        assessment.status = 'completed'
        assessment.completed_at = timezone.now()
        assessment.save(update_fields=['status', 'completed_at'])
        messages.success(request, 'تم حفظ تقرير المراجعة الداخلي. هذه مراجعة داخلية ولا '
                                  'تمثل شهادة امتثال رسمية أو اعتماداً من أي جهة.')
        return redirect('auditor_portal:dashboard')
    return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
