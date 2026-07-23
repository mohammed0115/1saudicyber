"""
Auditor Portal Views — internal human review of a company's controls/evidence.

INTERNAL review only. This portal NEVER issues an official certification or
accreditation and never marks a company "certified" — that would contradict the
platform's stated positioning. It records auditor notes, document requests, and a
final internal audit report. Access + object scoping are enforced per auditor.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, HttpResponseForbidden
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from core.roles import company_portal_required
from compliance.models import Assessment, CompanyControl, Evidence, InvalidAssessmentTransition
from .models import (AuditorNote, DocumentRequest, AuditReport, AuditorControlVerdict,
                     AuditorControlVerdictHistory, CompanyRFIResponse)

# Verdict validation: which negative/partial states require a written rationale /
# recommendation before the internal verdict can be saved.
_RATIONALE_REQUIRED = {'partially_compliant', 'non_compliant', 'needs_more_evidence', 'not_applicable'}
_RECOMMENDATION_REQUIRED = {'non_compliant', 'needs_more_evidence'}


def _require_live_engagement(user, company):
    """P0-01 defense: an auditor may act on a company's assessment ONLY while a LIVE accepted
    assignment exists. Closes the "access persists after de-assignment" gap — the assessment
    row keeps assigned_auditor after an assignment is cancelled/rejected, so scoping by
    assigned_auditor alone is not enough. Platform admins are exempt (explicit). Raises Http404
    (not 403) so a de-provisioned auditor cannot even tell the assessment still exists.
    """
    from core.roles import is_platform_admin_user
    if is_platform_admin_user(user):
        return
    from auditors.services import has_accepted_assignment
    if not has_accepted_assignment(user, company):
        raise Http404('No live assignment to this company.')


def _assigned_assessment_or_404(request, assessment_id):
    """Resolve an Assessment assigned to this auditor AND still backed by a live accepted
    assignment. Single entry point used everywhere the auditor portal loads an assessment."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    _require_live_engagement(request.user, assessment.company)
    return assessment


_LOCKED_MSG = 'هذا التقييم مُغلق بعد إصدار تقريره الداخلي النهائي ولا يقبل تعديلات جديدة.'


def _reject_if_locked(assessment):
    """P0-02: a finalized (terminal) assessment is immutable. Return a 403 response to return
    from the view when it is locked, else None. Applied at EVERY artifact-mutation entry point
    (verdict/finding/CAPA/note/RFI) so a closed assessment can never be edited server-side,
    regardless of what the UI shows."""
    if assessment is not None and assessment.is_locked:
        return HttpResponseForbidden(_LOCKED_MSG)
    return None


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
            # A pending/suspended auditor HAS a profile but isn't active. Send them to
            # their auditor home (which explains their status), NOT dashboard:main —
            # dashboard:main routes role=='auditor' back here, causing an infinite
            # redirect loop (ERR_TOO_MANY_REDIRECTS).
            from auditors.services import get_auditor_profile
            if get_auditor_profile(request.user) is not None:
                return redirect('auditors:dashboard')
            messages.error(request, 'الوصول مرفوض. يلزم حساب مدقّق فعّال.')
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
        _, created = Assessment.objects.get_or_create(
            company=asg.company, assigned_auditor=user,
            defaults=dict(assessment_type='formal_audit', status='auditor_review',
                          started_at=timezone.now()),
        )
        # DD-fix: advance the (previously dead) Company lifecycle when audit begins.
        # NOTE: 'certified'/'expired' stay intentionally unset — this platform performs an
        # INTERNAL readiness review and never issues an official certification.
        if created and asg.company.status in ('registered', 'classified'):
            asg.company.status = 'in_assessment'
            asg.company.save(update_fields=['status'])


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
        'attention': _auditor_attention(request.user),
    }
    return render(request, 'auditor_portal/dashboard.html', context)


def _auditor_attention(user):
    """Cross-assessment 'requires your attention' aggregate for the auditor.

    Read-only. Buckets every assessment assigned to THIS auditor by what the
    auditor must do next. Reuses review_workspace_summary (existing data only) —
    never writes, never issues a compliance decision.
    """
    from .workspace import review_workspace_summary
    assessments = (Assessment.objects.filter(assigned_auditor=user)
                   .select_related('company').order_by('-created_at'))
    awaiting_review, rfi_responses, awaiting_verdict, recently_completed = [], [], [], []
    tot = {'unreviewed': 0, 'rfi_responses': 0, 'open_rfi': 0, 'assessments': assessments.count()}
    for a in assessments:
        s = review_workspace_summary(a)
        row = {'assessment': a, 'company': a.company, 'summary': s}
        tot['unreviewed'] += s['unreviewed_controls']
        tot['rfi_responses'] += s['responded_rfi']
        tot['open_rfi'] += s['open_rfi']
        if a.status == 'completed':
            recently_completed.append(row)
            continue
        if s['responded_rfi'] > 0:
            rfi_responses.append(row)
        if s['unreviewed_controls'] > 0:
            awaiting_review.append(row)
        elif s['reviewed_controls'] > 0 and not s['has_report'] and s['open_rfi'] == 0:
            # every control reviewed, no open RFI, but the internal report is not issued yet.
            awaiting_verdict.append(row)
    return {
        'totals': tot,
        'awaiting_review': awaiting_review,
        'rfi_responses': rfi_responses,
        'awaiting_verdict': awaiting_verdict,
        'recently_completed': recently_completed[:5],
    }


@login_required
@auditor_required
def review_queue(request):
    """Centralized cross-company review queue for the assigned auditor."""
    ensure_assessments_for_auditor(request.user)
    return render(request, 'auditor_portal/review_queue.html',
                  {'attention': _auditor_attention(request.user)})


@login_required
@auditor_required
def review_assessment(request, assessment_id):
    """Review a specific assessment — view all controls and evidence (own assignment only)."""
    assessment = _assigned_assessment_or_404(request, assessment_id)
    company_controls = (CompanyControl.objects.filter(company=assessment.company)
                        .select_related('control', 'control__framework', 'control__domain')
                        .order_by('control__domain__order', 'control__control_id'))
    from .workspace import review_workspace_summary
    verdict_map = {v.company_control_id: v for v in
                   AuditorControlVerdict.objects.filter(assessment=assessment)}
    for cc in company_controls:
        cc.verdict = verdict_map.get(cc.id)
    from .findings_service import assessment_maturity
    from .models import AuditFinding
    findings = list(AuditFinding.objects.filter(assessment=assessment)
                    .select_related('company_control__control'))
    context = {
        'assessment': assessment,
        'company_controls': company_controls,
        'notes': AuditorNote.objects.filter(assessment=assessment),
        'document_requests': DocumentRequest.objects.filter(assessment=assessment),
        'workspace': review_workspace_summary(assessment),
        'maturity': assessment_maturity(assessment),   # G1 maturity scorecard
        # H3 — assessment-level findings roll-up.
        'findings': findings,
        'open_findings_count': sum(1 for f in findings if f.is_open),
    }
    return render(request, 'auditor_portal/review_assessment.html', context)


@login_required
@auditor_required
def review_control(request, assessment_id, control_id):
    """Review a specific control's evidence (own assignment + own company only)."""
    assessment = _assigned_assessment_or_404(request, assessment_id)
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    evidences = Evidence.objects.filter(company_control=company_control).order_by('-uploaded_at')
    verdict = AuditorControlVerdict.objects.filter(
        assessment=assessment, company_control=company_control).first()
    # Prev/next navigation across the company's controls (stable order by control_id).
    ordered_ids = list(CompanyControl.objects.filter(company=assessment.company)
                       .order_by('control__control_id', 'id').values_list('id', flat=True))
    prev_id = next_id = None
    position = total_pos = None
    if company_control.id in ordered_ids:
        i = ordered_ids.index(company_control.id)
        total_pos = len(ordered_ids)
        position = i + 1
        prev_id = ordered_ids[i - 1] if i > 0 else None
        next_id = ordered_ids[i + 1] if i < total_pos - 1 else None
    from .models import AuditFinding
    context = {
        'assessment': assessment,
        'company_control': company_control,
        'prev_control_id': prev_id, 'next_control_id': next_id,
        'control_position': position, 'control_total': total_pos,
        'evidences': evidences,
        'notes': AuditorNote.objects.filter(assessment=assessment, company_control=company_control),
        'document_requests': (DocumentRequest.objects.filter(
            assessment=assessment, company_control=company_control)
            .prefetch_related('responses')),
        'verdict': verdict,
        # Append-only verdict trail (most recent first) — shown only when there's real history.
        'verdict_history': list(AuditorControlVerdictHistory.objects.filter(
            assessment=assessment, company_control=company_control)
            .select_related('auditor')[:20]),
        'verdict_status_choices': AuditorControlVerdict.STATUS_CHOICES,
        # G1 — implementation/maturity levels for the verdict form.
        'implementation_choices': AuditorControlVerdict.IMPLEMENTATION_CHOICES,
        # G2 — findings for this control + severity options for the create form.
        'findings': (AuditFinding.objects.filter(assessment=assessment, company_control=company_control)
                     .prefetch_related('corrective_actions')),
        'severity_choices': AuditFinding.SEVERITY_CHOICES,
    }
    return render(request, 'auditor_portal/review_control.html', context)


@login_required
@auditor_required
@require_POST
def add_note(request, assessment_id, control_id):
    """Add an auditor note to a control (POST-only; tenant-scoped to the assessment).

    F-AUDIT: hardened to @require_POST for parity with the other mutation views
    (save_verdict/submit_report/RFI). GET now 405s instead of silently redirecting;
    the inner request.method guard is kept as a harmless belt-and-braces check.
    """
    if request.method == 'POST':
        assessment = _assigned_assessment_or_404(request, assessment_id)
        locked = _reject_if_locked(assessment)
        if locked:
            return locked
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
    assessment = _assigned_assessment_or_404(request, assessment_id)
    locked = _reject_if_locked(assessment)
    if locked:
        return locked
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
    # G1 — framework-native implementation/maturity level (optional; feeds the domain %).
    implementation_level = request.POST.get('implementation_level', '')
    if implementation_level not in dict(AuditorControlVerdict.IMPLEMENTATION_CHOICES):
        implementation_level = ''
    # P0-02: the current verdict upsert and its append-only history row persist together.
    with transaction.atomic():
        AuditorControlVerdict.objects.update_or_create(
            assessment=assessment, company_control=company_control,
            defaults=dict(auditor=request.user, status=status, rationale=rationale,
                          recommendation=recommendation, impact=impact,
                          implementation_level=implementation_level, reviewed_at=timezone.now()))
        # Append-only audit trail: preserve every verdict change (who/what/when) for defensibility.
        AuditorControlVerdictHistory.objects.create(
            assessment=assessment, company_control=company_control, auditor=request.user,
            status=status, implementation_level=implementation_level, impact=impact,
            rationale=rationale, recommendation=recommendation)
    messages.success(request, 'تم حفظ الحكم الداخلي على الضابط.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
@require_POST
def add_finding(request, assessment_id, control_id):
    """G2 — record an audit finding (non-conformity/observation) on a control.

    Own assignment + own company only (mirrors save_verdict's scoping). The finding drives
    the corrective-action (CAPA) lifecycle. Internal review artefact — not a certification.
    """
    from .findings_service import create_finding
    assessment = _assigned_assessment_or_404(request, assessment_id)
    locked = _reject_if_locked(assessment)
    if locked:
        return locked
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    try:
        finding = create_finding(
            assessment, company_control, request.user,
            severity=request.POST.get('severity', ''),
            title=request.POST.get('title', ''),
            description=request.POST.get('description', ''),
            root_cause=request.POST.get('root_cause', ''),
            evidence_reference=request.POST.get('evidence_reference', ''))
        from .notifications import notify_new_finding
        notify_new_finding(finding)   # best-effort email to the company (never blocks)
        messages.success(request, 'تم تسجيل الملاحظة.')
    except ValueError:
        messages.error(request, 'أدخل درجة صحيحة وعنوانًا ووصفًا للملاحظة.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


def _parse_date(raw):
    from datetime import date
    try:
        return date.fromisoformat(raw) if raw else None
    except (ValueError, TypeError):
        return None


def _back_to_control(finding):
    return redirect('auditor_portal:review_control',
                    assessment_id=finding.assessment_id, control_id=finding.company_control_id)


@login_required
@auditor_required
@require_POST
def add_corrective_action(request, finding_id):
    """G2 CAPA — auditor records a corrective action on a finding (own assignment only)."""
    from .models import AuditFinding
    from .findings_service import add_corrective_action as _add
    finding = get_object_or_404(AuditFinding, id=finding_id, assessment__assigned_auditor=request.user)
    _require_live_engagement(request.user, finding.assessment.company)
    locked = _reject_if_locked(finding.assessment)
    if locked:
        return locked
    try:
        _add(finding, description=request.POST.get('description', ''),
             owner=request.POST.get('owner', ''), due_date=_parse_date(request.POST.get('due_date')),
             created_by=request.user)
        messages.success(request, 'تمت إضافة إجراء تصحيحي.')
    except ValueError:
        messages.error(request, 'وصف الإجراء التصحيحي مطلوب.')
    return _back_to_control(finding)


@login_required
@auditor_required
@require_POST
def update_finding_status(request, finding_id):
    """G2 — auditor advances a finding through its lifecycle (own assignment only)."""
    from .models import AuditFinding
    from .findings_service import transition_finding
    finding = get_object_or_404(AuditFinding, id=finding_id, assessment__assigned_auditor=request.user)
    _require_live_engagement(request.user, finding.assessment.company)
    locked = _reject_if_locked(finding.assessment)
    if locked:
        return locked
    try:
        transition_finding(finding, request.POST.get('status', ''))
        from .notifications import notify_finding_status
        notify_finding_status(finding)   # tell the company the finding's status changed
        messages.success(request, 'تم تحديث حالة الملاحظة.')
    except ValueError:
        messages.error(request, 'انتقال حالة غير صالح.')
    return _back_to_control(finding)


@login_required
@auditor_required
@require_POST
def verify_corrective_action(request, action_id):
    """G2 — auditor re-verifies a corrective action (own assignment only)."""
    from .models import CorrectiveAction
    from .findings_service import verify_corrective_action as _verify
    action = get_object_or_404(CorrectiveAction, id=action_id,
                               finding__assessment__assigned_auditor=request.user)
    _require_live_engagement(request.user, action.finding.assessment.company)
    locked = _reject_if_locked(action.finding.assessment)
    if locked:
        return locked
    _verify(action, note=request.POST.get('note', ''), mark_verified=True)
    from .notifications import notify_capa_verified
    notify_capa_verified(action)   # tell the company their CAPA was verified
    messages.success(request, 'تم التحقّق من الإجراء التصحيحي.')
    return _back_to_control(action.finding)


@login_required
@company_portal_required
def company_findings(request):
    """G2 — company view of audit findings on its own controls (read + add CAPA)."""
    from .models import AuditFinding
    findings = (AuditFinding.objects.filter(company_control__company=request.user.company)
                .select_related('company_control__control')
                .prefetch_related('corrective_actions'))
    return render(request, 'auditor_portal/company_findings.html', {'findings': findings})


@login_required
@company_portal_required
@require_POST
def company_add_corrective_action(request, finding_id):
    """G2 — the company proposes/updates a corrective action for a finding on its control."""
    from .models import AuditFinding
    from .findings_service import add_corrective_action as _add
    finding = get_object_or_404(AuditFinding, id=finding_id,
                                company_control__company=request.user.company)
    locked = _reject_if_locked(finding.assessment)
    if locked:
        return locked
    try:
        _add(finding, description=request.POST.get('description', ''),
             owner=request.POST.get('owner', ''), due_date=_parse_date(request.POST.get('due_date')),
             created_by=request.user)
        from .notifications import notify_company_capa
        notify_company_capa(finding)   # tell the auditor a remediation plan was proposed
        messages.success(request, 'تمت إضافة خطة معالجة.')
    except ValueError:
        messages.error(request, 'وصف خطة المعالجة مطلوب.')
    return redirect('auditor_portal:company_findings')


@login_required
@company_portal_required
@require_POST
def company_update_capa(request, action_id):
    """G2 — company advances its corrective action (planned → in_progress → done)."""
    from .models import CorrectiveAction
    from .findings_service import advance_corrective_action
    action = get_object_or_404(CorrectiveAction, id=action_id,
                               finding__company_control__company=request.user.company)
    locked = _reject_if_locked(action.finding.assessment)
    if locked:
        return locked
    try:
        advance_corrective_action(action, request.POST.get('status', ''))
        messages.success(request, 'تم تحديث حالة خطة المعالجة.')
    except ValueError:
        messages.error(request, 'انتقال حالة غير صالح.')
    return redirect('auditor_portal:company_findings')


@login_required
def message_thread(request, company_id):
    """G5 — one internal message thread per company (company users + assigned auditor + staff).

    A user with no access gets a safe 404 (never reveals the thread). Read-only rendering;
    posting is a separate POST endpoint.
    """
    from core.models import Company
    from .models import CompanyMessage
    from .messaging import can_access_thread, sender_role_label
    company = get_object_or_404(Company, id=company_id)
    if not can_access_thread(request.user, company):
        raise Http404()
    thread = CompanyMessage.objects.filter(company=company).select_related('sender')
    for m in thread:
        m.role_label = sender_role_label(m.sender)
    return render(request, 'auditor_portal/message_thread.html',
                  {'company': company, 'thread': thread})


@login_required
@require_POST
def post_message(request, company_id):
    """G5 — post a message to a company's thread (same access set as message_thread)."""
    from core.models import Company
    from .models import CompanyMessage
    from .messaging import can_access_thread
    company = get_object_or_404(Company, id=company_id)
    if not can_access_thread(request.user, company):
        raise Http404()
    body = (request.POST.get('body', '') or '').strip()
    if body:
        msg = CompanyMessage.objects.create(company=company, sender=request.user, body=body[:4000])
        from .notifications import notify_new_message
        notify_new_message(msg)   # best-effort email to the other participants
    else:
        messages.error(request, 'اكتب رسالة قبل الإرسال.')
    return redirect('auditor_portal:message_thread', company_id=company.id)


@login_required
@auditor_required
@require_POST
def request_document(request, assessment_id, control_id):
    """Create an RFI (request for information/evidence) — title + reason + priority."""
    assessment = _assigned_assessment_or_404(request, assessment_id)
    locked = _reject_if_locked(assessment)
    if locked:
        return locked
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
        rfi = DocumentRequest.objects.create(
            assessment=assessment, company_control=company_control, auditor=request.user,
            title=title[:200], description=desc, description_ar=desc_ar,
            priority=priority, status='open')
        from .notifications import notify_new_rfi
        notify_new_rfi(rfi)   # best-effort email to the company (never blocks)
        messages.success(request, 'تم إرسال طلب الاستكمال إلى الشركة.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


def _auditor_rfi_or_404(request, rfi_id):
    """An RFI whose assessment belongs to the logged-in auditor AND a live engagement, else 404."""
    rfi = get_object_or_404(DocumentRequest, id=rfi_id, assessment__assigned_auditor=request.user)
    _require_live_engagement(request.user, rfi.assessment.company)
    return rfi


@login_required
@auditor_required
@require_POST
def close_rfi(request, rfi_id):
    """Auditor closes an RFI (closing note required)."""
    rfi = _auditor_rfi_or_404(request, rfi_id)
    locked = _reject_if_locked(rfi.assessment)
    if locked:
        return locked
    note = (request.POST.get('closing_note', '') or '').strip()
    if rfi.status not in DocumentRequest.OPEN_STATES:
        messages.info(request, 'هذا الطلب مغلق بالفعل.')
        return redirect('auditor_portal:review_control', assessment_id=rfi.assessment_id,
                        control_id=rfi.company_control.control_id)
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
    locked = _reject_if_locked(rfi.assessment)
    if locked:
        return locked
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
    locked = _reject_if_locked(rfi.assessment)
    if locked:
        return locked
    # State-machine guard: only a closed/cancelled RFI can be reopened.
    if rfi.status not in ('closed', 'cancelled'):
        messages.info(request, 'هذا الطلب مفتوح بالفعل.')
        return redirect('auditor_portal:review_control', assessment_id=rfi.assessment_id,
                        control_id=rfi.company_control.control_id)
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
    locked = _reject_if_locked(rfi.assessment)
    if locked:
        return locked
    text = (request.POST.get('response_text', '') or '').strip()
    attachment = request.FILES.get('attachment')
    # Validate the optional attachment with the SAME guard used for evidence uploads
    # (magic-byte + extension allowlist + size cap) — never trust a raw upload.
    if attachment is not None:
        from django.conf import settings
        from compliance.upload_validation import validate_evidence_file
        allowed = getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', [])
        max_size = getattr(settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)
        ok, _ext, _err = validate_evidence_file(attachment, allowed)
        if not ok:
            messages.error(request, 'نوع الملف المرفق غير مدعوم. الأنواع المدعومة: '
                           + '، '.join(e.upper() for e in allowed) + '.')
            return redirect('auditor_portal:company_rfi_list')
        if attachment.size > max_size:
            messages.error(request, 'الملف المرفق كبير جدًا. الحد الأقصى %d ميجابايت.' % (max_size // (1024 * 1024)))
            return redirect('auditor_portal:company_rfi_list')
    if not text:
        messages.error(request, 'نص الرد مطلوب.')
    else:
        CompanyRFIResponse.objects.create(request=rfi, responder=request.user,
                                          response_text=text, attachment=attachment)
        if rfi.status in ('open', 'pending', 'under_review'):
            rfi.status = 'responded'
            rfi.responded_at = timezone.now()
            rfi.save(update_fields=['status', 'responded_at'])
        from .notifications import notify_rfi_response
        notify_rfi_response(rfi)   # tell the auditor the company answered
        messages.success(request, 'تم إرسال ردك إلى المدقق.')
    return redirect('auditor_portal:company_rfi_list')


@login_required
def download_rfi_attachment(request, response_id):
    """P0-01: authenticated, tenant-scoped download of an RFI response attachment.

    RFI attachments are stored privately (never a public /media/ URL). Access is limited to the
    owning company, a platform admin, or an auditor with a LIVE accepted assignment to that
    company (mirrors the evidence-download / de-provisioning boundary). An unknown or foreign id
    returns a safe 404 — it never reveals the attachment exists or leaks the stored path.
    """
    from core.files import serve_authorized_file
    resp = (CompanyRFIResponse.objects
            .select_related('request__company_control__company')
            .filter(id=response_id).first())
    if resp is None or not resp.attachment:
        raise Http404()
    company = resp.request.company_control.company
    user = request.user
    allowed = (user.is_staff or user.is_superuser
               or getattr(user, 'company_id', None) == company.id)
    if not allowed:
        from auditors.services import has_accepted_assignment
        allowed = has_accepted_assignment(user, company)
    if not allowed:
        raise Http404()
    return serve_authorized_file(
        resp.attachment,
        download_name=resp.attachment.name.rsplit('/', 1)[-1])


@login_required
@auditor_required
@require_POST
def submit_report(request, assessment_id):
    """Submit the final INTERNAL audit report (POST-only; own assignment only).

    Records the internal report and closes the assessment. It does NOT issue any
    certificate and NEVER marks the company "certified" — this is an internal
    readiness review, not an official certification/accreditation.

    F-AUDIT: hardened to @require_POST for parity with the other mutation views;
    GET now 405s. The inner request.method guard is kept as belt-and-braces.
    """
    if request.method == 'POST':
        # Authorize (assigned auditor + live engagement) on an unlocked read first.
        _assigned_assessment_or_404(request, assessment_id)
        # Validate the verdict against the report's own choices — never store an arbitrary value.
        verdict = request.POST.get('verdict', 'fail')
        if verdict not in dict(AuditReport._meta.get_field('verdict').choices):
            messages.error(request, 'قيمة الحكم غير صالحة.')
            return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
        try:
            with transaction.atomic():
                # Lock the row so concurrent submits (double-POST, browser/proxy/Celery retry)
                # serialize: the loser sees 'completed' after the winner commits. Re-check the
                # terminal state AFTER acquiring the lock (race-safe issue-once).
                assessment = (Assessment.objects.select_for_update()
                              .get(pk=assessment_id, assigned_auditor=request.user))
                if assessment.status == 'completed':
                    messages.info(request, 'التقرير الداخلي لهذا التقييم مُصدَر بالفعل.')
                    return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
                # Readiness guard: cannot finalize while RFIs are still open (hard block); warn
                # (but allow) when no internal verdict has been recorded yet.
                open_rfi = DocumentRequest.objects.filter(
                    assessment=assessment, status__in=DocumentRequest.OPEN_STATES).count()
                if open_rfi:
                    messages.error(request, 'لا يمكن إصدار التقرير الداخلي النهائي قبل إغلاق طلبات '
                                            'الاستكمال المفتوحة (%d طلب مفتوح).' % open_rfi)
                    return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
                reviewed = AuditorControlVerdict.objects.filter(
                    assessment=assessment, status__in=AuditorControlVerdict.REVIEWED_STATES).count()
                total_controls = CompanyControl.objects.filter(company=assessment.company).count()
                if reviewed == 0:
                    messages.warning(request, 'تنبيه: لا توجد أحكام داخلية مسجّلة على الضوابط بعد. '
                                              'هذا تقرير داخلي مبدئي.')
                elif total_controls and reviewed < total_controls:
                    messages.warning(request, 'تنبيه: لم تُراجع كل الضوابط بعد — هذا تقرير مراجعة '
                                              'داخلي مبدئي وليس نهائياً.')
                # H1 — serialize the audit-core (findings + maturity) into the report so the
                # deliverable is a SNAPSHOT of the work at finalization, not just a verdict.
                from .models import AuditFinding
                from .findings_service import assessment_maturity
                findings_payload = [{
                    'control_id': getattr(f.company_control.control, 'control_id', ''),
                    'severity': f.severity, 'severity_ar': f.severity_ar,
                    'title': f.title, 'status': f.status, 'status_ar': f.status_ar,
                    'corrective_actions': f.corrective_actions.count(),
                } for f in (AuditFinding.objects.filter(assessment=assessment)
                            .select_related('company_control__control')
                            .prefetch_related('corrective_actions'))]
                # Report write + state transition happen together, atomically. The OneToOne on
                # AuditReport.assessment guarantees at most one report per assessment.
                AuditReport.objects.update_or_create(
                    assessment=assessment,
                    defaults=dict(auditor=request.user, verdict=verdict,
                                  executive_summary=request.POST.get('executive_summary', ''),
                                  executive_summary_ar=request.POST.get('executive_summary_ar', ''),
                                  findings=findings_payload,
                                  recommendations=[assessment_maturity(assessment)]),
                )
                assessment.completed_at = timezone.now()
                # Formal transition (validates auditor_review/draft -> completed; refuses illegal).
                assessment.transition_to('completed', update_fields=['completed_at'])
        except InvalidAssessmentTransition:
            messages.error(request, 'لا يمكن إصدار التقرير من حالة التقييم الحالية.')
            return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
        messages.success(request, 'تم حفظ تقرير المراجعة الداخلي. هذه مراجعة داخلية ولا '
                                  'تمثل شهادة امتثال رسمية أو اعتماداً من أي جهة.')
        return redirect('auditor_portal:dashboard')
    return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
