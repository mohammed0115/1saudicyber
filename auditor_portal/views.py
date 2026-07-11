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
from django.views.decorators.http import require_POST
from core.roles import company_portal_required
from compliance.models import Assessment, CompanyControl, Evidence
from .models import (AuditorNote, DocumentRequest, AuditReport, AuditorControlVerdict,
                     CompanyRFIResponse)

# Verdict validation: which negative/partial states require a written rationale /
# recommendation before the internal verdict can be saved.
_RATIONALE_REQUIRED = {'partially_compliant', 'non_compliant', 'needs_more_evidence', 'not_applicable'}
_RECOMMENDATION_REQUIRED = {'non_compliant', 'needs_more_evidence'}


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
    verdict_map = {v.company_control_id: v for v in
                   AuditorControlVerdict.objects.filter(assessment=assessment)}
    for cc in company_controls:
        cc.verdict = verdict_map.get(cc.id)
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
    verdict = AuditorControlVerdict.objects.filter(
        assessment=assessment, company_control=company_control).first()
    context = {
        'assessment': assessment,
        'company_control': company_control,
        'evidences': evidences,
        'notes': AuditorNote.objects.filter(assessment=assessment, company_control=company_control),
        'document_requests': (DocumentRequest.objects.filter(
            assessment=assessment, company_control=company_control)
            .prefetch_related('responses')),
        'verdict': verdict,
        'verdict_status_choices': AuditorControlVerdict.STATUS_CHOICES,
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
@require_POST
def save_verdict(request, assessment_id, control_id):
    """Record/replace the auditor's INTERNAL verdict for a control (own assignment only)."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    status = request.POST.get('status', '')
    if status not in dict(AuditorControlVerdict.STATUS_CHOICES) or status == 'not_reviewed':
        messages.error(request, 'اختر حالة حكم داخلي صحيحة.')
        return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)
    rationale = (request.POST.get('rationale', '') or '').strip()
    recommendation = (request.POST.get('recommendation', '') or '').strip()
    if status in _RATIONALE_REQUIRED and not rationale:
        messages.error(request, 'المبرر مطلوب لهذه الحالة.')
        return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)
    if status in _RECOMMENDATION_REQUIRED and not recommendation:
        messages.error(request, 'التوصية مطلوبة لهذه الحالة.')
        return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)
    impact = request.POST.get('impact', '')
    if impact not in dict(AuditorControlVerdict.IMPACT_CHOICES):
        impact = ''
    AuditorControlVerdict.objects.update_or_create(
        assessment=assessment, company_control=company_control,
        defaults=dict(auditor=request.user, status=status, rationale=rationale,
                      recommendation=recommendation, impact=impact, reviewed_at=timezone.now()))
    messages.success(request, 'تم حفظ الحكم الداخلي على الضابط.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
@require_POST
def request_document(request, assessment_id, control_id):
    """Create an RFI (request for information/evidence) — title + reason + priority."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    title = (request.POST.get('title', '') or '').strip()
    desc = (request.POST.get('description', '') or '').strip()
    desc_ar = (request.POST.get('description_ar', '') or '').strip()
    priority = request.POST.get('priority', 'medium')
    if priority not in dict(DocumentRequest.PRIORITY_CHOICES):
        priority = 'medium'
    if not title or not (desc or desc_ar):
        messages.error(request, 'عنوان الطلب وسبب/وصف المطلوب مطلوبان.')
    else:
        DocumentRequest.objects.create(
            assessment=assessment, company_control=company_control, auditor=request.user,
            title=title[:200], description=desc, description_ar=desc_ar,
            priority=priority, status='open')
        messages.success(request, 'تم إرسال طلب الاستكمال إلى الشركة.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


def _auditor_rfi_or_404(request, rfi_id):
    """An RFI whose assessment belongs to the logged-in auditor, else 404."""
    return get_object_or_404(DocumentRequest, id=rfi_id, assessment__assigned_auditor=request.user)


@login_required
@auditor_required
@require_POST
def close_rfi(request, rfi_id):
    """Auditor closes an RFI (closing note required)."""
    rfi = _auditor_rfi_or_404(request, rfi_id)
    note = (request.POST.get('closing_note', '') or '').strip()
    if not note:
        messages.error(request, 'سبب/ملاحظة الإغلاق مطلوبة.')
    else:
        rfi.status = 'closed'
        rfi.closing_note = note
        rfi.closed_at = timezone.now()
        rfi.save(update_fields=['status', 'closing_note', 'closed_at'])
        messages.success(request, 'تم إغلاق طلب الاستكمال.')
    return redirect('auditor_portal:review_control', assessment_id=rfi.assessment_id,
                    control_id=rfi.company_control_id)


@login_required
@auditor_required
@require_POST
def cancel_rfi(request, rfi_id):
    """Auditor cancels an RFI."""
    rfi = _auditor_rfi_or_404(request, rfi_id)
    rfi.status = 'cancelled'
    rfi.closed_at = timezone.now()
    rfi.save(update_fields=['status', 'closed_at'])
    messages.success(request, 'تم إلغاء طلب الاستكمال.')
    return redirect('auditor_portal:review_control', assessment_id=rfi.assessment_id,
                    control_id=rfi.company_control_id)


@login_required
@auditor_required
@require_POST
def reopen_rfi(request, rfi_id):
    """Auditor reopens a closed/cancelled RFI (asks for further clarification)."""
    rfi = _auditor_rfi_or_404(request, rfi_id)
    rfi.status = 'open'
    rfi.closed_at = None
    rfi.save(update_fields=['status', 'closed_at'])
    messages.success(request, 'تم إعادة فتح طلب الاستكمال.')
    return redirect('auditor_portal:review_control', assessment_id=rfi.assessment_id,
                    control_id=rfi.company_control_id)


# ---------- Company-side RFI (company users only; NOT the auditor portal guard) ----------
@login_required
@company_portal_required
def company_rfi_list(request):
    """The company sees auditor RFIs addressed to it and can respond (own company only)."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    rfis = (DocumentRequest.objects.filter(company_control__company=company)
            .select_related('company_control', 'company_control__control', 'assessment')
            .prefetch_related('responses').order_by('-created_at'))
    return render(request, 'auditor_portal/company_rfi_list.html', {
        'company': company, 'rfis': rfis})


@login_required
@company_portal_required
@require_POST
def company_rfi_respond(request, rfi_id):
    """Company responds to an RFI for its OWN company (text; optional linked evidence)."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    rfi = get_object_or_404(DocumentRequest, id=rfi_id, company_control__company=company)
    text = (request.POST.get('response_text', '') or '').strip()
    if not text:
        messages.error(request, 'نص الرد مطلوب.')
    else:
        CompanyRFIResponse.objects.create(request=rfi, responder=request.user, response_text=text)
        if rfi.status in ('open', 'pending', 'under_review'):
            rfi.status = 'responded'
            rfi.responded_at = timezone.now()
            rfi.save(update_fields=['status', 'responded_at'])
        messages.success(request, 'تم إرسال ردك إلى المدقق.')
    return redirect('auditor_portal:company_rfi_list')


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
        # Readiness guard: cannot finalize while RFIs are still open (hard block); warn
        # (but allow) when no internal verdict has been recorded yet.
        open_rfi = DocumentRequest.objects.filter(
            assessment=assessment, status__in=DocumentRequest.OPEN_STATES).count()
        if open_rfi:
            messages.error(request, 'لا يمكن إصدار التقرير الداخلي النهائي قبل إغلاق طلبات '
                                    'الاستكمال المفتوحة (%d طلب مفتوح).' % open_rfi)
            return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
        if not AuditorControlVerdict.objects.filter(
                assessment=assessment, status__in=AuditorControlVerdict.REVIEWED_STATES).exists():
            messages.warning(request, 'تنبيه: لا توجد أحكام داخلية مسجّلة على الضوابط بعد. '
                                      'هذا تقرير داخلي مبدئي.')
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
