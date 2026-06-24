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
from .models import Framework, Domain, Control, CompanyControl, Evidence, Assessment
from ai_engine.services import process_uploaded_file, analyze_evidence
from ai_engine.models import AIAuditLog


@login_required
def controls_list(request):
    """Display all applicable controls for the user's company."""
    company = request.user.company
    if not company:
        messages.error(request, 'No company associated with your account.')
        return redirect('dashboard:main')

    # Get applicable frameworks
    frameworks = Framework.objects.filter(is_active=True)
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

    domains = Domain.objects.all()
    if selected_framework:
        domains = domains.filter(framework__code=selected_framework)

    context = {
        'frameworks': frameworks,
        'domains': domains,
        'controls': controls,
        'company_controls': company_controls,
        'selected_framework': selected_framework,
        'selected_domain': selected_domain,
    }
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
    }
    return render(request, 'compliance/control_detail.html', context)


@login_required
def upload_evidence(request, control_id):
    """Upload evidence for a specific control and trigger AI analysis."""
    if request.method != 'POST':
        return redirect('compliance:control_detail', control_id=control_id)

    control = get_object_or_404(Control, id=control_id)
    company = request.user.company
    company_control, _ = CompanyControl.objects.get_or_create(company=company, control=control)

    uploaded_file = request.FILES.get('evidence_file')
    if not uploaded_file:
        messages.error(request, 'Please select a file to upload.')
        return redirect('compliance:control_detail', control_id=control_id)

    # Determine file type
    file_ext = os.path.splitext(uploaded_file.name)[1].lower().replace('.', '')

    # Server-side validation (FR-005.11): reject unsupported types / oversized files.
    allowed = getattr(settings, 'ALLOWED_EVIDENCE_EXTENSIONS', [])
    max_size = getattr(settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)
    if file_ext not in allowed:
        messages.error(
            request,
            f'Unsupported file type ".{file_ext}". Allowed types: {", ".join(allowed)}.'
        )
        return redirect('compliance:control_detail', control_id=control_id)
    if uploaded_file.size > max_size:
        messages.error(
            request,
            f'File too large ({uploaded_file.size // (1024*1024)} MB). '
            f'Maximum allowed is {max_size // (1024*1024)} MB.'
        )
        return redirect('compliance:control_detail', control_id=control_id)

    # Create evidence record
    evidence = Evidence.objects.create(
        company_control=company_control,
        uploaded_by=request.user,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        file_type=file_ext,
        file_size=uploaded_file.size,
        status='processing',
    )

    # Run OCR + AI through the shared pipeline. Use Celery if a broker is reachable,
    # otherwise process synchronously so the platform works without extra infra.
    from compliance.services import process_evidence_pipeline
    try:
        try:
            from monitoring.tasks import analyze_evidence_async
            analyze_evidence_async.delay(evidence.id)
            messages.success(request, 'Evidence uploaded. AI analysis is running in the background.')
        except Exception:
            result = process_evidence_pipeline(evidence.id)
            messages.success(request, f'Evidence analyzed. AI Verdict: {result.get("verdict", "pending")}')
    except Exception as e:
        evidence.status = 'uploaded'
        evidence.save()
        messages.error(request, f'Error processing file: {str(e)}')

    return redirect('compliance:control_detail', control_id=control_id)


# ============================================================
# Phase 3I — Journey dashboard (read-only overview + next step)
# ============================================================
@login_required
def journey_dashboard(request):
    """Read-only end-to-end workflow overview for the user's company.

    Tenant-scoped; never writes, never creates CompanyControl, never lets AI
    decide compliance. Pure status/navigation hardening.
    """
    from .user_journey import (build_company_journey_status,
                               get_next_recommended_action, calculate_journey_progress)
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'compliance/journey_dashboard.html', {
        'company': company,
        'stages': build_company_journey_status(company),
        'next_action': get_next_recommended_action(company),
        'progress': calculate_journey_progress(company),
        'is_staff': request.user.is_staff,
    })


# ============================================================
# Phase 3B — Company Intake Wizard + Applicable Framework Review
# ============================================================
from .forms import CompanyIntakeForm
from .models import CompanyIntakeProfile, FrameworkApplicabilityResult, FrameworkVersion
from .framework_applicability import evaluate_company, RULES, _is_available


@login_required
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
            messages.success(request, 'تم حفظ ملف التصنيف وتحديد الأطر المنطبقة.')
            return redirect('compliance:applicability_review')
    else:
        form = CompanyIntakeForm(instance=profile)
    return render(request, 'compliance/intake.html', {'form': form, 'company': company,
                                                       'has_profile': profile is not None})


@login_required
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
    for s in scopes:
        s.official_count = counts.get(s.framework_version_id, 0)

    unavailable = []
    for code in ('NCA-OTCC-1-2022', 'NCA-DCC-1-2022'):
        fv = FrameworkVersion.objects.filter(code=code).first()
        if fv and not _is_available(fv):
            unavailable.append(fv)
    return render(request, 'compliance/applicability_review.html', {
        'company': company,
        'results': results,
        'scopes': scopes,
        'unavailable': unavailable,
        'can_approve': request.user.is_staff,
        'has_profile': CompanyIntakeProfile.objects.filter(company=company).exists(),
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
        messages.success(request, f'تم اعتماد الإطار {scope.framework_version.code}.')
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
                            'framework_scope__framework_version'))
    return render(request, 'compliance/control_plan.html', {
        'company': company, 'approved': approved, 'plan': plan,
        'can_generate': request.user.is_staff,
    })


# ============================================================
# Phase 3D — Evidence Checklist planning page (no upload form here)
# ============================================================
@login_required
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
             .prefetch_related('submissions'))
    return render(request, 'compliance/evidence_checklist.html', {
        'company': company, 'items': items, 'can_generate': request.user.is_staff,
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
@require_http_methods(["GET", "POST"])
def evidence_upload_v2(request, item_id):
    """Upload an EvidenceSubmission for a checklist item (tenant-scoped). No AI/OCR."""
    import hashlib, os
    from .forms import EvidenceSubmissionForm
    from .models import EvidenceSubmission
    item = _company_checklist_item(request, item_id)
    if item is None:
        messages.error(request, 'عنصر القائمة غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')

    if request.method == 'POST':
        form = EvidenceSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data['uploaded_file']
            ext = os.path.splitext(f.name)[1].lower().lstrip('.')
            digest = hashlib.sha256()
            for chunk in f.chunks():
                digest.update(chunk)
            f.seek(0)
            version = item.submissions.count() + 1
            EvidenceSubmission.objects.create(
                company=request.user.company, checklist_item=item, uploaded_file=f,
                original_filename=f.name, file_type=ext, file_size=f.size,
                file_hash=digest.hexdigest(), version=version, status='pending_review',
                uploaded_by=request.user, notes=form.cleaned_data.get('notes', ''))
            # Reflect progress on the checklist item (NOT a compliance decision).
            if item.status in ('planned', 'in_progress'):
                item.status = 'submitted'
                item.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'تم رفع الدليل وربطه بعنصر القائمة (قيد المراجعة).')
            return redirect('compliance:evidence_submission_list', item_id=item.id)
    else:
        form = EvidenceSubmissionForm()
    return render(request, 'compliance/evidence_upload_v2.html', {'item': item, 'form': form})


@login_required
def evidence_submission_list(request, item_id):
    """List submissions for a checklist item (tenant-scoped)."""
    item = _company_checklist_item(request, item_id)
    if item is None:
        messages.error(request, 'عنصر القائمة غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    return render(request, 'compliance/evidence_submission_list.html', {
        'item': item, 'submissions': item.submissions.all()})


@login_required
def evidence_submission_detail(request, submission_id):
    """Submission detail (tenant-scoped to the user's company)."""
    from .models import EvidenceSubmission
    sub = EvidenceSubmission.objects.filter(id=submission_id, company=request.user.company).first()
    if sub is None:
        messages.error(request, 'الدليل غير موجود أو لا يخصّ شركتك.')
        return redirect('compliance:evidence_checklist')
    analysis = getattr(sub, 'analysis', None)
    return render(request, 'compliance/evidence_submission_detail.html',
                  {'submission': sub, 'analysis': analysis, 'can_analyze': request.user.is_staff})


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
@login_required
def reports_index(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from .reporting import get_approved_framework_versions
    from .models import ControlAssessment
    reviewed_count = (ControlAssessment.objects.filter(company=company)
                      .exclude(status='not_reviewed').count())
    return render(request, 'compliance/reports_index.html', {
        'company': company, 'frameworks': get_approved_framework_versions(company),
        'reviewed_assessment_count': reviewed_count})


@login_required
def report_executive_summary(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from .reporting import build_executive_summary
    return render(request, 'compliance/report_executive_summary.html',
                  {'company': company, 'summary': build_executive_summary(company)})


@login_required
def report_gap_analysis(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from .reporting import build_framework_gap_analysis
    return render(request, 'compliance/report_gap_analysis.html',
                  {'company': company, 'frameworks': build_framework_gap_analysis(company)})


@login_required
def report_evidence_matrix(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from .reporting import build_evidence_matrix
    return render(request, 'compliance/report_evidence_matrix.html',
                  {'company': company, 'rows': build_evidence_matrix(company)})


@login_required
def report_framework(request, framework_version_id):
    """Framework-filtered report (gap + matrix), scoped to an approved framework version."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
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
