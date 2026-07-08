"""
Compliance Views - Controls listing, Evidence upload, AI Analysis
"""
import os
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from .models import Framework, Domain, Control, CompanyControl, Evidence, Assessment
from ai_engine.services import process_uploaded_file, analyze_evidence
from ai_engine.models import AIAuditLog
from core.roles import company_portal_required, email_verified_required


@login_required
@company_portal_required
def controls_list(request):
    """Display all applicable controls for the user's company."""
    company = request.user.company
    if not company:
        messages.error(request, _('لا توجد شركة مرتبطة بحسابك.'))
        return redirect('dashboard:main')

    selected_framework = request.GET.get('framework', '')
    selected_domain = request.GET.get('domain', '')

    controls = Control.objects.select_related('framework', 'domain')
    if selected_framework:
        controls = controls.filter(framework__code=selected_framework)
    if selected_domain:
        controls = controls.filter(domain_id=selected_domain)

    # Get company control statuses
    company_controls = {
        cc.control_id: cc for cc in
        CompanyControl.objects.filter(company=company).select_related('control')
    }

    # Populate filters from frameworks/domains that ACTUALLY have controls, so the
    # dropdowns can never appear empty while the library holds controls (Manus 8D-2).
    fw_ids = Control.objects.values_list('framework_id', flat=True).distinct()
    frameworks = Framework.objects.filter(id__in=fw_ids).order_by('name')
    domain_qs = Domain.objects.filter(
        id__in=Control.objects.values_list('domain_id', flat=True).distinct())
    if selected_framework:
        domain_qs = domain_qs.filter(framework__code=selected_framework)
    domains = domain_qs.order_by('name')

    context = {
        'frameworks': frameworks,
        'domains': domains,
        'controls': controls,
        'company_controls': company_controls,
        'selected_framework': selected_framework,
        'selected_domain': selected_domain,
        'has_filter_options': frameworks.exists() or domains.exists(),
    }
    from .journey import build_page_guide
    context['guide'] = build_page_guide(company, 'controls')
    return render(request, 'compliance/controls_list.html', context)


@login_required
def control_detail(request, control_id):
    """View a specific control and its evidence."""
    control = get_object_or_404(Control, id=control_id)
    company = request.user.company

    company_control, created = CompanyControl.objects.get_or_create(
        company=company, control=control
    )
    evidences = Evidence.objects.filter(company_control=company_control).order_by('-uploaded_at')

    # Get cross-mapped controls
    mapped_controls = control.mapped_controls.all()

    context = {
        'control': control,
        'company_control': company_control,
        'evidences': evidences,
        'mapped_controls': mapped_controls,
        # Honest AI state: only claim "processing" when automated analysis is actually
        # configured. Otherwise the evidence is simply awaiting human review.
        'ai_enabled': bool((getattr(settings, 'OPENAI_API_KEY', '') or '').strip()),
    }
    return render(request, 'compliance/control_detail.html', context)


@login_required
@email_verified_required
def upload_evidence(request, control_id):
    """Upload evidence for a specific control and trigger AI analysis."""
    if request.method != 'POST':
        return redirect('compliance:control_detail', control_id=control_id)

    control = get_object_or_404(Control, id=control_id)
    company = request.user.company
    # Tenant guard: uploads always require the user's own company context; never crash
    # (e.g. a staff/unlinked account has no company -> get_or_create(company=None) would fail).
    if company is None:
        messages.error(request, 'رفع الأدلة يتطلّب سياق شركة · Evidence upload requires a company context.')
        return redirect('compliance:control_detail', control_id=control_id)

    uploaded_file = request.FILES.get('evidence_file')
    if not uploaded_file:
        messages.error(request, _('يرجى اختيار ملف للرفع.'))
        return redirect('compliance:control_detail', control_id=control_id)

    # Server-side validation (FR-005.11 + P0-6): reject spoofed types via magic bytes,
    # unsupported types, and oversized files.
    from .upload_validation import validate_evidence_file
    allowed = getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', [])
    max_size = getattr(settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)
    ok, file_ext, err = validate_evidence_file(uploaded_file, allowed)
    if not ok:
        messages.error(request, f'{err} Allowed types: {", ".join(allowed)}.')
        return redirect('compliance:control_detail', control_id=control_id)
    if uploaded_file.size > max_size:
        messages.error(
            request,
            f'File too large ({uploaded_file.size // (1024*1024)} MB). '
            f'Maximum allowed is {max_size // (1024*1024)} MB.'
        )
        return redirect('compliance:control_detail', control_id=control_id)

    # Create the evidence record. A file-storage or DB failure (e.g. MEDIA_ROOT not
    # writable) must NEVER 500 or leak a server path — fail with a safe message.
    # NB: use `created` (not `_`) so the gettext alias `_` is not shadowed.
    try:
        company_control, created = CompanyControl.objects.get_or_create(
            company=company, control=control)
        evidence = Evidence.objects.create(
            company_control=company_control,
            uploaded_by=request.user,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_type=file_ext,
            file_size=uploaded_file.size,
            status='processing',
        )
    except Exception:
        messages.error(request, 'تعذّر حفظ الدليل بأمان. حاول مرة أخرى. '
                                '· Could not save the evidence safely. Please try again.')
        return redirect('compliance:control_detail', control_id=control_id)

    # Advisory OCR/AI pipeline (best-effort). Use Celery if a broker is reachable,
    # otherwise process synchronously. A failure keeps the evidence record and shows a
    # safe status — it never 500s and never exposes an exception/path to the user.
    from compliance.services import process_evidence_pipeline
    try:
        # Only dispatch to the broker when async is explicitly enabled (worker running);
        # otherwise process synchronously with no broker connection attempt.
        if getattr(settings, 'EVIDENCE_ASYNC_ENABLED', False):
            try:
                from monitoring.tasks import analyze_evidence_async
                analyze_evidence_async.delay(evidence.id)
            except Exception:
                process_evidence_pipeline(evidence.id)
        else:
            process_evidence_pipeline(evidence.id)
        messages.success(request, _('تم رفع الدليل. التحليل الاستشاري قيد التنفيذ ولا يُعد قرارًا نهائيًا.'))
    except Exception:
        try:
            evidence.status = 'uploaded'
            evidence.save(update_fields=['status'])
        except Exception:
            pass
        messages.warning(request, 'تم حفظ الدليل، وتعذّر إكمال التحليل الاستشاري الآن. '
                                  '· Evidence saved; advisory analysis could not complete right now.')

    return redirect('compliance:control_detail', control_id=control_id)


# ============================================================
# Phase 3I — Journey dashboard (read-only overview + next step)
# ============================================================
@login_required
@company_portal_required
def journey_dashboard(request):
    """Read-only end-to-end workflow overview for the user's company.

    Tenant-scoped; never writes, never creates CompanyControl, never lets AI
    decide compliance. Pure status/navigation hardening.
    """
    from .user_journey import (build_company_journey_status,
                               get_next_recommended_action, calculate_journey_progress)
    from billing.subscription_access import company_has_active_subscription
    from .workflow_stepper import build_company_workflow_stepper
    from risk.services import risk_dashboard_counts
    from monitoring.continuous import summarize_company_monitoring
    from .journey import build_company_compliance_journey
    from .smart_classification import classify_company
    from .applicability_engine import evaluate_company_applicability
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'compliance/journey_dashboard.html', {
        'company': company,
        'journey': build_company_compliance_journey(company, request.user),
        'stages': build_company_journey_status(company),
        'next_action': get_next_recommended_action(company),
        'progress': calculate_journey_progress(company),
        'is_staff': request.user.is_staff,
        'subscription_active': company_has_active_subscription(company),
        'stepper': build_company_workflow_stepper(company),
        'risk_counts': risk_dashboard_counts(company),
        'monitoring_summary': summarize_company_monitoring(company),
        'classification': classify_company(company),
        'applicability': evaluate_company_applicability(company),
    })


@login_required
@company_portal_required
def evidence_extraction_preview(request, submission_id):
    """Phase 6C / 6C-FIX-A — text-extraction preview for one evidence submission.

    Tenant-scoped and read-only: shows the PERSISTED extraction result if one
    exists, otherwise a truthful "not attempted yet" state with a run button.
    No OCR, no AI, no compliance judgment; never leaks the file path.
    """
    from .models import EvidenceSubmission
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    return render(request, 'compliance/evidence_extraction.html', {
        'submission': sub,
        'extraction': getattr(sub, 'text_extraction', None),
    })


@login_required
@company_portal_required
@require_http_methods(["POST"])
def run_evidence_extraction(request, submission_id):
    """Phase 6C-FIX-A — run + persist a safe text-extraction attempt (owner-only).

    POST only, CSRF-protected, tenant-scoped. The only write is the single
    EvidenceTextExtraction row (upsert). No OCR, no AI, no external calls.
    """
    from .models import EvidenceSubmission
    from .evidence_extraction import (save_extraction_for_submission,
                                      record_evidence_audit, MANUAL_REVIEW_STATUSES)
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    obj = save_extraction_for_submission(sub)
    # Audit the run + resulting status (success / failure / manual-review) safely.
    record_evidence_audit(request.user, request.user.company, 'extraction', sub,
                          status=obj.status, extra={'char_count': obj.char_count,
                                                    'method': obj.extraction_method})
    if obj.has_text:
        messages.success(request, 'تم استخراج النص من الدليل · Text extraction complete.')
    elif obj.status == 'failed':
        messages.error(request, 'تعذر تنفيذ الاستخراج بأمان · Extraction failed safely.')
    elif obj.status in MANUAL_REVIEW_STATUSES:
        messages.warning(request, 'يتطلب هذا الملف مراجعة يدوية — لا تتوفّر طبقة نص قابلة للاستخراج (OCR غير مفعّل). '
                                  '· Manual review required — no extractable text layer (OCR not available yet).')
    else:
        messages.warning(request, 'تعذر استخراج نص كافٍ من هذا الملف · Not enough text could be extracted.')
    return redirect('compliance:evidence_extraction', submission_id=sub.id)


@login_required
def evidence_ai_analysis_preview(request, submission_id):
    """Phase 6D — advisory AI analysis preview for one evidence submission (read-only).

    Tenant-scoped. Shows the persisted advisory result or a gated/not-run state.
    No final compliance decision; never leaks the file path or secrets.
    """
    from .models import EvidenceSubmission
    from .evidence_ai_analyzer import can_analyze_submission
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    can_run, reason = can_analyze_submission(sub)
    # R1: reflect the AI-service availability (residency/key), not just the extraction gate,
    # so the user knows upfront why analysis may be unavailable and how to enable it.
    from ai_engine.services import ai_advisory_state
    ai_available, ai_reason = ai_advisory_state()
    return render(request, 'compliance/evidence_ai_analysis.html', {
        'submission': sub,
        'analysis': getattr(sub, 'ai_analysis', None),
        'can_run': can_run and ai_available,
        'gate_reason': reason if not can_run else (ai_reason if not ai_available else ''),
        'ai_available': ai_available,
        'ai_reason': ai_reason,
    })


@login_required
@require_http_methods(["POST"])
def run_evidence_ai_analysis(request, submission_id):
    """Phase 6D — run + persist advisory AI analysis (owner-only, POST, gated)."""
    from .models import EvidenceSubmission
    from .evidence_ai_analyzer import can_analyze_submission, analyze_submission_evidence
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    can_run, reason = can_analyze_submission(sub)
    if not can_run:
        messages.error(request, reason)
        return redirect('compliance:evidence_ai_analysis', submission_id=sub.id)
    obj = analyze_submission_evidence(sub, actor=request.user)
    if obj.status == 'completed':
        messages.success(request, 'تم تشغيل التحليل الاستشاري. النتيجة استشارية ولا تُعد قرارًا نهائيًا.')
    elif obj.status == 'skipped':
        # R1: surface the SPECIFIC reason (residency / no key / extraction) instead of a vague one.
        messages.warning(request, obj.error_message or 'خدمة التحليل الاستشاري غير متاحة حاليًا.')
    else:
        messages.error(request, 'تعذر تنفيذ التحليل الاستشاري بأمان.')
    return redirect('compliance:evidence_ai_analysis', submission_id=sub.id)


@login_required
def evidence_rule_evaluation_preview(request, submission_id):
    """Phase 6E — system-suggested (non-final) status preview for one submission.

    Tenant-scoped, read-only render of the persisted suggestion. No final verdict,
    no certification; never leaks the file path.
    """
    from .models import EvidenceSubmission
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    return render(request, 'compliance/evidence_rule_evaluation.html', {
        'submission': sub,
        'evaluation': getattr(sub, 'rule_evaluation', None),
    })


@login_required
@require_http_methods(["POST"])
def run_evidence_rule_evaluation(request, submission_id):
    """Phase 6E — run + persist the deterministic suggested status (owner-only, POST)."""
    from .models import EvidenceSubmission
    from .rule_engine import evaluate_submission_rules
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    obj = evaluate_submission_rules(sub, actor=request.user)
    if obj.status == 'completed':
        messages.success(request, 'تم إنشاء حالة نظامية مقترحة. النتيجة بانتظار مراجعة المدقق.')
    else:
        messages.warning(request, 'تعذر إنشاء حالة نظامية مقترحة لهذا الدليل.')
    return redirect('compliance:evidence_rule_evaluation', submission_id=sub.id)


@login_required
@require_http_methods(["GET", "POST"])
def auditor_verdict_view(request, submission_id):
    """Phase 6F — auditor/staff final-verdict review for one submission.

    GET renders the full review context (extraction + advisory AI + rule suggestion).
    POST records a human reviewer verdict (staff/superuser or assigned active auditor
    only). Company users may view their own but never submit. Internal decision only —
    never a certificate; never finalizes reports.
    """
    from .models import EvidenceSubmission
    from .auditor_verdict import (can_view_submission_review, can_submit_final_verdict,
                                  allowed_statuses_for, record_auditor_final_verdict, VerdictError)
    sub = EvidenceSubmission.objects.filter(id=submission_id).first()
    if sub is None or not can_view_submission_review(request.user, sub):
        messages.error(request, 'الدليل غير موجود أو لا تملك صلاحية عرضه.')
        return redirect('compliance:evidence_checklist')

    can_submit = can_submit_final_verdict(request.user, sub)
    if request.method == 'POST':
        if not can_submit:
            messages.error(request, 'يمكنك عرض القرار، ولا تملك صلاحية تعديله.')
            return redirect('compliance:auditor_verdict', submission_id=sub.id)
        try:
            record_auditor_final_verdict(
                sub, request.user,
                status=request.POST.get('status', ''),
                rationale=request.POST.get('rationale', ''),
                confidence=request.POST.get('confidence') or None,
                required_actions=[a for a in request.POST.getlist('required_actions') if a.strip()],
            )
            messages.success(request, 'تم حفظ قرار المدقق. هذه مراجعة داخلية فقط.')
        except VerdictError as e:
            messages.error(request, str(e))
        return redirect('compliance:auditor_verdict', submission_id=sub.id)

    return render(request, 'compliance/auditor_verdict.html', {
        'submission': sub,
        'extraction': getattr(sub, 'text_extraction', None),
        'ai_analysis': getattr(sub, 'ai_analysis', None),
        'rule_evaluation': getattr(sub, 'rule_evaluation', None),
        'verdict': getattr(sub, 'auditor_final_verdict', None),
        'can_submit': can_submit,
        'allowed_statuses': allowed_statuses_for(sub),
    })


@login_required
@company_portal_required
def applicability_preview(request):
    """Phase 6B — advisory control-applicability preview for the user's own company.

    Read-only and tenant-scoped: deterministic scope-based applicability only. Never
    writes, never creates CompanyControl / ControlApplicabilityResult / Assessment
    rows, never runs AI, never produces a compliance status or a final verdict.
    """
    from .applicability_engine import evaluate_company_applicability
    from .journey import build_page_guide
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'compliance/applicability_preview.html', {
        'company': company,
        'preview': evaluate_company_applicability(company),
        'guide': build_page_guide(company, 'applicability'),
    })


@login_required
@company_portal_required
def classification_summary(request):
    """Phase 6A — advisory Smart Classification summary for the user's own company.

    Read-only and tenant-scoped: deterministic advisory classification only. Never
    writes, never creates CompanyControl/applicability rows, never runs AI, and
    never issues a final compliance decision.
    """
    from .smart_classification import classify_company
    from .journey import build_page_guide, build_journey_nav
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'compliance/classification.html', {
        'company': company,
        'classification': classify_company(company),
        'guide': build_page_guide(company, 'classification'),
        'nav': build_journey_nav(company, 'classification'),
    })


# ============================================================
# Phase 3B — Company Intake Wizard + Applicable Framework Review
# ============================================================
from .forms import CompanyIntakeForm
from .models import CompanyIntakeProfile, FrameworkApplicabilityResult, FrameworkVersion
from .framework_applicability import evaluate_company, RULES, _is_available


@login_required
@company_portal_required
def intake_wizard(request):
    """Create/update the company's intake profile, then evaluate framework applicability.

    Scoped to request.user.company (a user only ever sees their own company's intake).
    Never creates CompanyControl / Evidence / EvidenceRequirement.
    """
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    profile = CompanyIntakeProfile.objects.filter(company=company).first()
    if request.method == 'POST':
        form = CompanyIntakeForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.company = company
            profile.review_status = 'completed'
            profile.completed_at = timezone.now()
            profile.save()
            # Deterministic applicability evaluation (writes FrameworkApplicabilityResult only).
            evaluate_company(company, apply=True)
            # UAT-5: an intake change invalidates any previously APPROVED scope — it must be
            # re-approved before final workflows (control plan / reports / submit) proceed.
            from .models import CompanyFrameworkScope
            invalidated = CompanyFrameworkScope.objects.filter(
                company=company, status='approved').update(status='needs_review')
            # UAT-7: audit the intake change (best-effort; never blocks the save).
            try:
                from core.models import AuditLog
                AuditLog.objects.create(user=request.user, company=company, action='intake_saved',
                                        method='POST', path=request.path,
                                        metadata={'scopes_invalidated': invalidated})
            except Exception:
                pass
            if invalidated:
                messages.info(request, 'تم تحديث الإدخال؛ يلزم إعادة اعتماد نطاق الأطر قبل المتابعة.')
            messages.success(request, 'تم حفظ ملف التصنيف وتحديد الأطر المنطبقة.')
            return redirect('compliance:applicability_review')
    else:
        form = CompanyIntakeForm(instance=profile)
    from .journey import build_journey_nav
    from .workflow_stepper import build_company_workflow_stepper
    return render(request, 'compliance/intake.html', {'form': form, 'company': company,
                                                       'has_profile': profile is not None,
                                                       'stepper': build_company_workflow_stepper(company),
                                                       'nav': build_journey_nav(company, 'intake')})


@login_required
@company_portal_required
def applicability_review(request):
    """Show framework applicability + proposed/approved scopes for the user's company."""
    from django.db.models import Count, Q
    from .models import CompanyFrameworkScope, Control
    from .framework_scope import propose_framework_scopes

    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Idempotently sync proposed scopes from applicability results (never clobbers approved/rejected).
    propose_framework_scopes(company, apply=True)

    results = (FrameworkApplicabilityResult.objects
               .filter(company=company)
               .select_related('framework_version', 'framework_version__framework'))
    scopes = (CompanyFrameworkScope.objects
              .filter(company=company)
              .select_related('framework_version', 'framework_version__framework'))
    # official control count per framework version (for display).
    counts = {fv: n for fv, n in Control.objects
              .filter(is_legacy_import=False, framework_version__isnull=False)
              .values_list('framework_version').annotate(n=Count('id'))}
    # A framework is company-visible only if its official controls are imported (available).
    # Filter in the BACKEND (not just templates): company users must never see legacy/unavailable
    # frameworks — they would imply a compliance scope the product cannot actually deliver yet.
    available_ids = set(counts.keys())
    is_staff = request.user.is_staff
    if not is_staff:
        results = results.filter(framework_version_id__in=available_ids)
        scopes = scopes.filter(framework_version_id__in=available_ids)
    for s in scopes:
        s.official_count = counts.get(s.framework_version_id, 0)

    # Unavailable (not-yet-imported) frameworks are shown to internal/admin staff only.
    unavailable = []
    if is_staff:
        for code in ('NCA-OTCC-1-2022', 'NCA-DCC-1-2022'):
            fv = FrameworkVersion.objects.filter(code=code).first()
            if fv and not _is_available(fv):
                unavailable.append(fv)
    # Company-facing review defaults to applicable/proposed frameworks only. Non-applicable
    # decisions are moved to a collapsed "advanced" section so the default view is not cluttered
    # with frameworks the company does not need (backend split, not just template CSS).
    applicable_results = [r for r in results if r.decision != 'not_applicable']
    not_applicable_results = [r for r in results if r.decision == 'not_applicable']
    from .journey import build_page_guide, build_journey_nav
    return render(request, 'compliance/applicability_review.html', {
        'company': company,
        'results': applicable_results,
        'not_applicable_results': not_applicable_results,
        'scopes': scopes,
        'unavailable': unavailable,
        'can_approve': request.user.is_staff,
        'has_profile': CompanyIntakeProfile.objects.filter(company=company).exists(),
        # UI: only surface the control-plan CTA once a scope is actually approved (a plan exists).
        'has_approved_scope': scopes.filter(status='approved').exists(),
        'guide': build_page_guide(company, 'applicability'),
        'nav': build_journey_nav(company, 'applicability'),
    })


@login_required
@company_portal_required
def framework_controls_preview(request, code):
    """Read-only preview of the official controls under a framework (by code), for the company's OWN
    applicable/proposed frameworks. Creates NOTHING (no control plan / evidence). Reused by BOTH the
    classification page (advisory proposed) and the scope review page. GET only.
    Validates the framework is applicable/proposed for request.user.company; otherwise 404.
    """
    from django.http import Http404
    from .models import (FrameworkVersion, Control, CompanyFrameworkScope,
                         FrameworkApplicabilityResult)
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    fv = FrameworkVersion.objects.filter(code=code).first()
    if fv is None:
        raise Http404('الإطار غير موجود.')
    # Applicable to THIS company: a non-rejected scope row, an applicable result, OR an advisory
    # "indicated" recommendation from the company's own smart classification (proposed frameworks).
    applicable = (
        CompanyFrameworkScope.objects.filter(company=company, framework_version=fv)
        .exclude(status='rejected').exists()
        or FrameworkApplicabilityResult.objects.filter(
            company=company, framework_version=fv, decision='applicable').exists())
    if not applicable:
        try:
            from .smart_classification import classify_company
            applicable = fv.code in {r.code for r in classify_company(company).indicated}
        except Exception:
            applicable = False
    if not applicable:
        raise Http404('هذا الإطار غير منطبق على شركتك.')
    controls = (Control.objects.filter(framework_version=fv, is_legacy_import=False)
                .select_related('domain')
                .prefetch_related('evidence_requirements')
                .order_by('control_id'))
    # Has the control plan been generated yet? (drives per-control status label; read-only).
    from .models import ControlApplicabilityResult
    plan_generated = ControlApplicabilityResult.objects.filter(
        company=company, control__framework_version=fv, decision='applicable').exists()
    # Paginate (backend) — long official-control lists (e.g. 108) must not render all at once.
    from django.core.paginator import Paginator
    total_controls = controls.count()
    page_obj = Paginator(controls, 15).get_page(request.GET.get('page'))
    return render(request, 'compliance/framework_controls_preview.html', {
        'company': company, 'fv': fv, 'controls': page_obj, 'page_obj': page_obj,
        'control_count': total_controls, 'plan_generated': plan_generated,
    })


def _get_company_scope(request, scope_id):
    """Fetch a scope scoped to the user's company (tenant isolation) or None."""
    from .models import CompanyFrameworkScope
    from .security import get_company_object_or_none
    return get_company_object_or_none(CompanyFrameworkScope, request.user.company, id=scope_id)


@login_required
@require_http_methods(["POST"])
def approve_framework_scope_view(request, scope_id):
    """Staff-only: approve a framework scope (scoped to the user's company)."""
    from .framework_scope import approve_framework_scope
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لاعتماد الإطار.')
        return redirect('compliance:applicability_review')
    scope = _get_company_scope(request, scope_id)
    if scope:
        approve_framework_scope(scope, user=request.user)
        # Chain generation so an approved scope immediately yields a control plan and
        # an evidence checklist — otherwise companies are stranded with 0 checklist
        # items (approved scope but nothing to upload against). Best-effort: a failure
        # here must never 500 the approval itself.
        planned = 0
        try:
            from .framework_scope import generate_control_applicability_plan
            from .evidence_planning import (generate_evidence_requirements,
                                            generate_evidence_checklist_for_company)
            generate_control_applicability_plan(request.user.company, scope, apply=True)
            generate_evidence_requirements(apply=True)
            res = generate_evidence_checklist_for_company(request.user.company, apply=True)
            planned = res.get('planned', 0) if isinstance(res, dict) else 0
        except Exception:
            planned = 0
        messages.success(
            request, 'تم اعتماد الإطار %s وتوليد خطة الضوابط وقائمة الأدلة (%d عنصر). '
                     '· Framework approved; control plan and evidence checklist generated.'
                     % (scope.framework_version.code, planned))
    return redirect('compliance:applicability_review')


@login_required
@require_http_methods(["POST"])
def reject_framework_scope_view(request, scope_id):
    """Staff-only: reject a framework scope."""
    from .framework_scope import reject_framework_scope
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لرفض الإطار.')
        return redirect('compliance:applicability_review')
    scope = _get_company_scope(request, scope_id)
    if scope:
        reject_framework_scope(scope, request.POST.get('reason', ''), user=request.user)
        messages.success(request, f'تم رفض الإطار {scope.framework_version.code}.')
    return redirect('compliance:applicability_review')


@login_required
@company_portal_required
@require_http_methods(["POST"])
def approve_company_scope(request):
    """Company-facing: the owner approves their OWN framework scope at journey step 4.

    Approves all proposed/needs_review scopes for request.user.company, then chains control-plan
    and evidence-checklist generation so the journey is never stranded. Tenant-scoped + audited.
    Never touches another company's data, classification logic, or the auditor workflow.
    """
    from .models import CompanyFrameworkScope
    from .framework_scope import (propose_framework_scopes, approve_framework_scope,
                                  generate_control_applicability_plan)
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    # Idempotently sync proposals from applicability results (never clobbers approved/rejected).
    propose_framework_scopes(company, apply=True)
    pending = CompanyFrameworkScope.objects.filter(
        company=company, status__in=['proposed', 'needs_review'])
    already = CompanyFrameworkScope.objects.filter(company=company, status='approved')
    if not pending.exists() and not already.exists():
        messages.info(request, 'لا توجد أطر منطبقة لاعتمادها. أكمل التصنيف الذكي أولًا لتحديد الأطر.')
        return redirect('compliance:classification')
    approved_codes = []
    for scope in pending:
        approve_framework_scope(scope, user=request.user)
        approved_codes.append(scope.framework_version.code)
    # Chain generation (best-effort; a failure must never 500 the approval).
    try:
        from .evidence_planning import (generate_evidence_requirements,
                                        generate_evidence_checklist_for_company)
        for scope in CompanyFrameworkScope.objects.filter(company=company, status='approved'):
            generate_control_applicability_plan(company, scope, apply=True)
        generate_evidence_requirements(apply=True)
        generate_evidence_checklist_for_company(company, apply=True)
    except Exception:
        pass
    try:
        from core.models import AuditLog
        AuditLog.objects.create(user=request.user, company=company, action='scope_approved',
                                method='POST', path=request.path,
                                metadata={'approved_frameworks': approved_codes})
    except Exception:
        pass
    messages.success(request, 'تم اعتماد نطاق الأطر. يمكنك الآن استعراض خطة الضوابط والمتابعة.')
    return redirect('compliance:control_plan')


@login_required
@require_http_methods(["POST"])
def generate_control_plan_view(request, scope_id):
    """Staff-only: generate the control applicability plan for an approved scope (separate button)."""
    from .framework_scope import generate_control_applicability_plan
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لتوليد خطة الضوابط.')
        return redirect('compliance:control_plan')
    scope = _get_company_scope(request, scope_id)
    if scope:
        count, _ = generate_control_applicability_plan(request.user.company, scope, apply=True)
        messages.success(request, f'تم تخطيط {count} ضابطاً رسمياً لإطار {scope.framework_version.code}.')
    return redirect('compliance:control_plan')


@login_required
@company_portal_required
def control_plan(request):
    """Read-only page: planned controls (ControlApplicabilityResult) for approved frameworks."""
    from .models import CompanyFrameworkScope, ControlApplicabilityResult
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    approved = (CompanyFrameworkScope.objects.filter(company=company, status='approved')
                .select_related('framework_version', 'framework_version__framework'))
    plan = (ControlApplicabilityResult.objects.filter(company=company)
            .select_related('control', 'control__framework', 'control__domain',
                            'framework_scope__framework_version')
            .order_by('control__framework_version__code', 'control__control_id'))
    # Paginate (backend) — a full plan can be 417 controls; never render them all at once.
    from django.core.paginator import Paginator
    plan_total = plan.count()
    plan_page = Paginator(plan, 20).get_page(request.GET.get('page'))
    from .journey import build_journey_nav
    from .workflow_stepper import build_company_workflow_stepper
    return render(request, 'compliance/control_plan.html', {
        'company': company, 'approved': approved, 'plan': plan_page, 'page_obj': plan_page,
        'plan_total': plan_total, 'can_generate': request.user.is_staff,
        'stepper': build_company_workflow_stepper(company),
        'nav': build_journey_nav(company, 'controls'),
    })


# ============================================================
# Phase 3D — Evidence Checklist planning page (no upload form here)
# ============================================================
@login_required
@company_portal_required
def evidence_checklist(request):
    """Read-only planned evidence checklist for the user's company (no upload here)."""
    from .models import EvidenceChecklistItem
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    items = (EvidenceChecklistItem.objects.filter(company=company)
             .select_related('evidence_requirement', 'evidence_requirement__control',
                             'evidence_requirement__control__framework_version',
                             'control_applicability_result')
             .prefetch_related('submissions')
             .order_by('evidence_requirement__control__framework_version__code',
                       'evidence_requirement__control__control_id'))
    # Paginate (backend) — a full checklist can be hundreds of items; never render all at once.
    from django.core.paginator import Paginator
    items_total = items.count()
    items_page = Paginator(items, 20).get_page(request.GET.get('page'))
    # Scope state drives a clear empty-state: no scopes -> classify; scopes pending
    # approval -> wait for approval; approved but empty -> (staff) generate.
    from .models import CompanyFrameworkScope, ControlApplicabilityResult
    scope_qs = CompanyFrameworkScope.objects.filter(company=company)
    has_any_scope = scope_qs.exists()
    has_approved_scope = scope_qs.filter(status='approved').exists()
    # Prerequisite for evidence: a generated control plan must exist.
    has_control_plan = ControlApplicabilityResult.objects.filter(
        company=company, decision='applicable').exists()
    from .workflow_stepper import build_company_workflow_stepper
    from .journey import build_page_guide, build_journey_nav
    return render(request, 'compliance/evidence_checklist.html', {
        'company': company, 'items': items_page, 'page_obj': items_page,
        'items_total': items_total, 'can_generate': request.user.is_staff,
        'has_any_scope': has_any_scope, 'has_approved_scope': has_approved_scope,
        'has_control_plan': has_control_plan,
        'stepper': build_company_workflow_stepper(company),
        'guide': build_page_guide(company, 'evidence'),
        'nav': build_journey_nav(company, 'evidence'),
    })


@login_required
@require_http_methods(["POST"])
def generate_evidence_checklist_view(request):
    """Staff-only: generate the company's evidence checklist plan (separate button)."""
    from .evidence_planning import generate_evidence_requirements, generate_evidence_checklist_for_company
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لتوليد قائمة الأدلة.')
        return redirect('compliance:evidence_checklist')
    company = request.user.company
    if company:
        generate_evidence_requirements(apply=True)  # ensure templates exist (official only)
        res = generate_evidence_checklist_for_company(company, apply=True)
        messages.success(request, f'تم تخطيط {res["planned"]} عنصر أدلة (من ضوابط رسمية منطبقة).')
    return redirect('compliance:evidence_checklist')


# ============================================================
# Phase 3E — Evidence Upload v2 (linked to EvidenceChecklistItem)
# Does NOT touch legacy upload_evidence / Evidence; no AI/OCR; no compliance decision.
# ============================================================
def _company_checklist_item(request, item_id):
    """Fetch a checklist item scoped to the user's company (tenant isolation) or None."""
    from .models import EvidenceChecklistItem
    from .security import get_company_object_or_none
    return get_company_object_or_none(EvidenceChecklistItem, request.user.company, id=item_id)


@login_required
@company_portal_required
@email_verified_required
@require_http_methods(["GET", "POST"])
def evidence_upload_v2(request, item_id):
    """Upload an EvidenceSubmission for a checklist item (tenant-scoped). No AI/OCR."""
    import hashlib, os
    from .forms import EvidenceSubmissionForm
    from .models import EvidenceSubmission
    from .evidence_extraction import record_evidence_audit
    item = _company_checklist_item(request, item_id)
    if item is None:
        messages.error(request, 'عنصر القائمة غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')

    if request.method == 'POST':
        # Plan gate: block only when the plan disables uploads or the file limit is reached.
        from billing.access import enforce_feature
        result, blocked = enforce_feature(request, request.user.company, 'evidence_upload')
        if blocked:
            messages.error(request, '%s · %s' % (result.message_ar, result.message_en))
            return redirect('billing:home')
        form = EvidenceSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            # URGENT hotfix: the upload must NEVER return 500, even if storage, hashing,
            # auditing, or an incomplete control/framework mapping misbehaves. Any
            # unexpected failure becomes a safe bilingual message + redirect.
            f = form.cleaned_data['uploaded_file']
            # P0-6: reject spoofed content types (magic-byte check) on this path too.
            from .upload_validation import validate_evidence_file
            _allowed = getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', [])
            _ok, ext, _err = validate_evidence_file(f, _allowed)
            if not _ok:
                messages.error(request, '%s · %s' % ('محتوى الملف لا يطابق امتداده.', _err))
                return redirect('compliance:evidence_submission_list', item_id=item.id)
            try:
                digest = hashlib.sha256()
                for chunk in f.chunks():
                    digest.update(chunk)
                f.seek(0)
                version = item.submissions.count() + 1
                sub = EvidenceSubmission.objects.create(
                    company=request.user.company, checklist_item=item, uploaded_file=f,
                    original_filename=f.name, file_type=ext, file_size=f.size,
                    file_hash=digest.hexdigest(), version=version, status='pending_review',
                    uploaded_by=request.user, notes=form.cleaned_data.get('notes', ''))
            except Exception:
                messages.error(request, 'تعذّر حفظ الدليل بأمان. حاول مرة أخرى. '
                                        '· Could not save the evidence safely. Please try again.')
                return redirect('compliance:evidence_submission_list', item_id=item.id)
            # Auditing + checklist status are best-effort and must never crash the upload.
            try:
                record_evidence_audit(request.user, request.user.company, 'uploaded', sub,
                                      status='pending_review')
            except Exception:
                pass
            try:
                if item.status in ('planned', 'in_progress'):
                    item.status = 'submitted'
                    item.save(update_fields=['status', 'updated_at'])
            except Exception:
                pass
            messages.success(request, 'تم رفع الدليل وربطه بعنصر القائمة (قيد المراجعة).')
            return redirect('compliance:evidence_submission_list', item_id=item.id)
    else:
        form = EvidenceSubmissionForm()
    return render(request, 'compliance/evidence_upload_v2.html', {'item': item, 'form': form})


@login_required
@company_portal_required
def evidence_submission_list(request, item_id):
    """List submissions for a checklist item (tenant-scoped)."""
    item = _company_checklist_item(request, item_id)
    if item is None:
        messages.error(request, 'عنصر القائمة غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    return render(request, 'compliance/evidence_submission_list.html', {
        'item': item, 'submissions': item.submissions.all()})


@login_required
@company_portal_required
def evidence_submission_detail(request, submission_id):
    """Submission detail (tenant-scoped to the user's company).

    Non-enumerable tenant isolation: a submission that is not the user's own
    (other company, unknown id, or no company) returns a safe 404 — it never
    reveals existence and never 500s. Anonymous users hit @login_required first.
    """
    from .models import EvidenceSubmission
    sub = get_object_or_404(EvidenceSubmission, id=submission_id, company=request.user.company)
    analysis = getattr(sub, 'analysis', None)
    extraction = getattr(sub, 'text_extraction', None)
    return render(request, 'compliance/evidence_submission_detail.html',
                  {'submission': sub, 'analysis': analysis, 'extraction': extraction,
                   'can_analyze': request.user.is_staff})


# ============================================================
# Phase 3F — Evidence analysis trigger (advisory). Staff-only to trigger.
# ============================================================
@login_required
@require_http_methods(["POST"])
def analyze_submission_view(request, submission_id):
    """Staff-only: run advisory analysis for a submission (tenant-scoped). No compliance decision."""
    from .models import EvidenceSubmission
    from .evidence_analysis import analyze_evidence_submission
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لتشغيل التحليل.')
        return redirect('compliance:evidence_checklist')
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    res = analyze_evidence_submission(sub, apply=True)
    messages.success(request, f'تم تشغيل التحليل الاستشاري (الحالة: {res.get("status")}). القرار النهائي للمدقّق.')
    return redirect('compliance:evidence_submission_detail', submission_id=sub.id)


# ============================================================
# Phase 3G — Auditor review + Control Assessment (staff-only to assess)
# ============================================================
@login_required
@company_portal_required
def auditor_review_queue(request):
    """Queue of the company's control assessments (applicable official controls)."""
    from .models import ControlAssessment
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    assessments = (ControlAssessment.objects.filter(company=company)
                   .select_related('control', 'control__framework_version', 'control__domain'))
    return render(request, 'compliance/auditor_review_queue.html', {
        'company': company, 'assessments': assessments, 'can_assess': request.user.is_staff})


@login_required
@require_http_methods(["GET", "POST"])
def auditor_review_detail(request, assessment_id):
    """Assessment detail + auditor decision form (staff-only to update). Tenant-scoped."""
    from .models import ControlAssessment, EvidenceChecklistItem, EvidenceSubmission, EvidenceAnalysisResult
    from .control_assessment import update_assessment_from_auditor_input
    company = request.user.company
    a = ControlAssessment.objects.filter(id=assessment_id, company=company).select_related(
        'control', 'control__framework_version').first()
    if a is None:
        messages.error(request, 'التقييم غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:auditor_review_queue')

    if request.method == 'POST':
        if not request.user.is_staff:
            messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق لاتخاذ القرار.')
            return redirect('compliance:auditor_review_detail', assessment_id=a.id)
        data = {
            'status': request.POST.get('status', a.status),
            'score': request.POST.get('score') or None,
            'auditor_notes': request.POST.get('auditor_notes', ''),
            'remediation_required': request.POST.get('remediation_required') == 'on',
            'remediation_plan': request.POST.get('remediation_plan', ''),
            'remediation_due_date': request.POST.get('remediation_due_date') or None,
            'risk_level': request.POST.get('risk_level', ''),
            'confidence_level': request.POST.get('confidence_level', ''),
        }
        update_assessment_from_auditor_input(a, data, request.user)
        messages.success(request, 'تم حفظ قرار التقييم (قرار المدقّق النهائي).')
        return redirect('compliance:auditor_review_detail', assessment_id=a.id)

    control = a.control
    reqs = control.evidence_requirements.all()
    submissions = EvidenceSubmission.objects.filter(
        company=company, checklist_item__evidence_requirement__control=control)
    analyses = EvidenceAnalysisResult.objects.filter(company=company, control=control)
    return render(request, 'compliance/auditor_review_detail.html', {
        'company': company, 'assessment': a, 'control': control,
        'requirements': reqs, 'submissions': submissions, 'analyses': analyses,
        'can_assess': request.user.is_staff,
        'status_choices': ControlAssessment.STATUS_CHOICES,
        'risk_choices': ControlAssessment.RISK_LEVEL_CHOICES,
        'confidence_choices': ControlAssessment.CONFIDENCE_CHOICES,
    })


@login_required
@require_http_methods(["POST"])
def generate_assessments_view(request):
    """Staff-only: create not_reviewed assessments for applicable official controls."""
    from .control_assessment import create_assessments_for_company
    if not request.user.is_staff:
        messages.error(request, 'يتطلّب صلاحية موظّف/مدقّق.')
        return redirect('compliance:auditor_review_queue')
    company = request.user.company
    if company:
        stats = create_assessments_for_company(company, apply=True)
        messages.success(request, f'تم إنشاء {stats["created"]} تقييماً (not_reviewed) للضوابط الرسمية المنطبقة.')
    return redirect('compliance:auditor_review_queue')


# ============================================================
# Phase 3H — Read-only compliance reports + gap analysis + exports
# ============================================================
# Phase 4B — report access is gated behind an active subscription (view + export).
# Report CALCULATIONS are unchanged; this only controls access to the output.
def _require_full_reports(request, company):
    """Return a subscription-required response if the company may not view full reports."""
    from billing.subscription_access import can_view_full_reports
    if can_view_full_reports(company):
        return None
    return render(request, 'compliance/subscription_required.html',
                  {'company': company, 'mode': 'view'})


def _require_report_export(request, company):
    """Return a subscription-required response if the company may not export reports."""
    from billing.subscription_access import can_export_reports
    if can_export_reports(company):
        return None
    return render(request, 'compliance/subscription_required.html',
                  {'company': company, 'mode': 'export'})


@login_required
@company_portal_required
def reports_index(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from .reporting import get_approved_framework_versions
    from .models import ControlAssessment
    from billing.subscription_access import company_has_active_subscription
    from .workflow_stepper import build_company_workflow_stepper
    from .journey import build_journey_nav
    reviewed_count = (ControlAssessment.objects.filter(company=company)
                      .exclude(status='not_reviewed').count())
    return render(request, 'compliance/reports_index.html', {
        'company': company, 'frameworks': get_approved_framework_versions(company),
        'reviewed_assessment_count': reviewed_count,
        'subscription_active': company_has_active_subscription(company),
        'stepper': build_company_workflow_stepper(company),
        'nav': build_journey_nav(company, 'reports')})


@login_required
@company_portal_required
def auditor_reviewed_report(request):
    """Phase 7B — internal auditor-reviewed report (subscription-gated, company-scoped).

    Read-only aggregation of AuditorFinalVerdict records. Internal review report —
    NOT a certificate or official accreditation. Preserves the existing report
    subscription gate; never finalizes/recalculates compliance numbers.
    """
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    gate = _require_full_reports(request, company)
    if gate:
        return gate
    from .report_finalization import build_auditor_reviewed_report
    from .journey import build_page_guide
    return render(request, 'compliance/auditor_reviewed_report.html', {
        'company': company,
        'report': build_auditor_reviewed_report(company),
        'guide': build_page_guide(company, 'auditor_report'),
    })


@login_required
@company_portal_required
def report_executive_summary(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    gate = _require_full_reports(request, company)
    if gate:
        return gate
    from .reporting import build_executive_summary
    return render(request, 'compliance/report_executive_summary.html',
                  {'company': company, 'summary': build_executive_summary(company)})


@login_required
@company_portal_required
def report_gap_analysis(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    gate = _require_full_reports(request, company)
    if gate:
        return gate
    from .reporting import build_framework_gap_analysis
    return render(request, 'compliance/report_gap_analysis.html',
                  {'company': company, 'frameworks': build_framework_gap_analysis(company)})


# ============================================================
# Phase 8F-GAP-ENGINE-A — deterministic internal-readiness gap dashboard.
# Internal, preliminary, evidence-based readiness (NOT an official certification).
# Not subscription-gated: companies can always see their preliminary readiness.
# ============================================================
@login_required
@company_portal_required
def gap_dashboard(request):
    """Read-only internal readiness dashboard for the user's company."""
    from .gap_engine import get_company_gap_summary, gap_rows, STATUS_AR
    company = request.user.company
    return render(request, 'compliance/gap_dashboard.html', {
        'company': company,
        'summary': get_company_gap_summary(company),
        'rows': gap_rows(company),
        'status_ar': STATUS_AR,
    })


@login_required
@company_portal_required
@require_http_methods(["POST"])
def run_gap_recalc(request):
    """POST-only: recalculate the deterministic gap analysis for the user's company."""
    from .gap_engine import recalculate_company_gap
    from billing.access import enforce_feature
    company = request.user.company
    result, blocked = enforce_feature(request, company, 'gap_analysis')
    if blocked:
        messages.error(request, '%s · %s' % (result.message_ar, result.message_en))
        return redirect('billing:home')
    summary = recalculate_company_gap(company, actor=request.user)
    messages.success(request, 'تم تحديث تحليل الفجوات (جاهزية أولية داخلية). '
                              '· Preliminary internal readiness recalculated (%d%%).'
                              % summary.get('overall_readiness_percent', 0))
    return redirect('compliance:gap_dashboard')


# ============================================================
# Phase 8H-REPORTING-A — internal commercial readiness report.
# Read-only aggregation of gap/risk/evidence; NOT an official certification.
# Not subscription-gated (internal readiness the company can always see).
# ============================================================
@login_required
@company_portal_required
def commercial_readiness_report(request):
    """Internal readiness report for the user's company (read-only)."""
    from .report_engine import build_commercial_readiness_report, record_report_audit
    from billing.access import enforce_feature
    company = request.user.company
    result, blocked = enforce_feature(request, company, 'commercial_reports')
    if blocked:
        return render(request, 'billing/feature_blocked.html', {
            'company': company, 'access': result,
            'feature_title': 'تقرير الجاهزية التجاري · Commercial readiness report'})
    report = build_commercial_readiness_report(company)
    record_report_audit(request.user, company, report, action='viewed')
    return render(request, 'compliance/commercial_readiness_report.html', {
        'company': company, 'report': report})


@login_required
@company_portal_required
@require_http_methods(["POST"])
def refresh_commercial_report(request):
    """POST-only: refresh the underlying data (gap + risks) then show the report."""
    from .gap_engine import recalculate_company_gap
    from .report_engine import build_commercial_readiness_report, record_report_audit
    from risk.risk_engine import generate_risks_from_gap
    from billing.access import enforce_feature
    company = request.user.company
    result, blocked = enforce_feature(request, company, 'commercial_reports')
    if blocked:
        messages.error(request, '%s · %s' % (result.message_ar, result.message_en))
        return redirect('billing:home')
    recalculate_company_gap(company, actor=request.user)
    generate_risks_from_gap(company, actor=request.user)
    report = build_commercial_readiness_report(company)
    record_report_audit(request.user, company, report, action='refreshed')
    messages.success(request, 'تم تجهيز تقرير الجاهزية الداخلي (%d%%). '
                              '· Internal readiness report prepared (%d%%).'
                              % (report['executive']['overall_readiness_percent'],
                                 report['executive']['overall_readiness_percent']))
    return redirect('compliance:commercial_readiness_report')


@login_required
@company_portal_required
def commercial_readiness_report_pdf(request):
    """Export the internal readiness report as a PDF (own company only)."""
    from django.http import HttpResponse
    from .report_pdf import build_commercial_readiness_pdf
    from .report_engine import build_commercial_readiness_report, record_report_audit
    from billing.access import enforce_feature
    company = request.user.company
    # Plan gate: block when the plan disables PDF export or the export limit is reached.
    result, blocked = enforce_feature(request, company, 'pdf_export')
    if blocked:
        messages.error(request, '%s · %s' % (result.message_ar, result.message_en))
        return redirect('compliance:commercial_readiness_report')
    try:
        pdf = build_commercial_readiness_pdf(company)
    except Exception:
        # No traceback/file path to the user; safe fallback to the HTML report.
        messages.error(request, 'تعذر تجهيز ملف PDF بأمان. حاول مرة أخرى أو استخدم الطباعة. '
                                '· Could not prepare the PDF safely. Try again or use Print.')
        return redirect('compliance:commercial_readiness_report')
    record_report_audit(request.user, company,
                        build_commercial_readiness_report(company), action='pdf_exported')
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = (
        'attachment; filename="1saudicyber_readiness_report_%s.pdf"' % company.id)
    return resp


@login_required
@company_portal_required
def report_evidence_matrix(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    gate = _require_full_reports(request, company)
    if gate:
        return gate
    from .reporting import build_evidence_matrix
    return render(request, 'compliance/report_evidence_matrix.html',
                  {'company': company, 'rows': build_evidence_matrix(company)})


@login_required
@company_portal_required
def report_framework(request, framework_version_id):
    """Framework-filtered report (gap + matrix), scoped to an approved framework version."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    gate = _require_full_reports(request, company)
    if gate:
        return gate
    from .reporting import (get_approved_framework_versions, build_framework_gap_analysis,
                            build_evidence_matrix)
    fv = next((f for f in get_approved_framework_versions(company) if f.id == framework_version_id), None)
    if fv is None:
        messages.error(request, 'الإطار غير معتمد لشركتك أو غير موجود.')
        return redirect('compliance:reports_index')
    gap = build_framework_gap_analysis(company, framework_version=fv)
    return render(request, 'compliance/report_framework.html', {
        'company': company, 'framework_version': fv,
        'gap': gap[0] if gap else None,
        'rows': build_evidence_matrix(company, framework_version=fv)})


@login_required
def export_evidence_matrix_csv(request):
    """CSV export of the evidence matrix (official controls only, tenant-scoped)."""
    import csv
    from django.http import HttpResponse
    from .reporting import build_evidence_matrix
    company = request.user.company
    if not company:
        return redirect('compliance:reports_index')
    gate = _require_report_export(request, company)
    if gate:
        return gate
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="evidence_matrix.csv"'
    w = csv.writer(resp)
    w.writerow(['framework', 'control_id', 'title', 'requirement_count', 'submission_count',
                'latest_submission_status', 'latest_ai_status', 'assessment_status'])
    for r in build_evidence_matrix(company):
        w.writerow([r['framework'], r['control_id'], r['title'], r['requirement_count'],
                    r['submission_count'], r['latest_submission_status'], r['latest_ai_status'],
                    r['assessment_status']])
    return resp


@login_required
def export_evidence_matrix_xlsx(request):
    """XLSX export of the evidence matrix (openpyxl)."""
    from django.http import HttpResponse
    from .reporting import build_evidence_matrix
    company = request.user.company
    if not company:
        return redirect('compliance:reports_index')
    gate = _require_report_export(request, company)
    if gate:
        return gate
    try:
        from openpyxl import Workbook
    except Exception:
        messages.error(request, 'تصدير Excel غير متاح (openpyxl غير مثبّت).')
        return redirect('compliance:report_evidence_matrix')
    wb = Workbook(); ws = wb.active; ws.title = 'Evidence Matrix'
    ws.append(['framework', 'control_id', 'title', 'requirement_count', 'submission_count',
               'latest_submission_status', 'latest_ai_status', 'assessment_status'])
    for r in build_evidence_matrix(company):
        ws.append([r['framework'], r['control_id'], r['title'], r['requirement_count'],
                   r['submission_count'], r['latest_submission_status'], r['latest_ai_status'],
                   r['assessment_status']])
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="evidence_matrix.xlsx"'
    wb.save(resp)
    return resp
