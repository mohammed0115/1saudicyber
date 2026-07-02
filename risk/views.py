"""Phase 5A — risk register & remediation views. Tenant-safe; auditor read-only."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .forms import RiskForm, RemediationTaskForm
from .models import RiskItem, RemediationTask
from . import services
from core.roles import company_portal_required


@login_required
@company_portal_required
def risk_list(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from compliance.journey import build_page_guide
    from .risk_engine import risk_generation_summary
    from django.db.models import Count
    risks_qs = services.company_risks(company).select_related('control', 'framework_version')
    status_counts = {row['status']: row['n'] for row in risks_qs.values('status').annotate(n=Count('id'))}
    return render(request, 'risk/risk_list.html', {
        'company': company,
        'risks': risks_qs,
        'counts': services.risk_dashboard_counts(company),
        'severity_counts': risk_generation_summary(company)['severity_counts'],
        'status_counts': status_counts,
        'guide': build_page_guide(company, 'risks'),
    })


@login_required
@company_portal_required
def risk_detail(request, risk_id):
    company = request.user.company
    risk = services.get_company_risk(company, risk_id)
    if risk is None:
        messages.error(request, 'الخطر غير موجود أو لا يخصّ شركتك.')
        return redirect('risk:list')
    return render(request, 'risk/risk_detail.html', {
        'company': company, 'risk': risk, 'tasks': risk.tasks.all()})


# ============================================================
# Phase 8G — deterministic Risk & Remediation generation from gap analysis.
# ============================================================
@login_required
@company_portal_required
@require_http_methods(["POST"])
def generate_risks(request):
    """POST-only: (re)generate internal risks + remediation from the gap analysis."""
    from .risk_engine import generate_risks_from_gap
    from billing.access import enforce_feature
    company = request.user.company
    result, blocked = enforce_feature(request, company, 'risk_engine')
    if blocked:
        messages.error(request, '%s · %s' % (result.message_ar, result.message_en))
        return redirect('billing:home')
    summary = generate_risks_from_gap(company, actor=request.user)
    messages.success(
        request, 'تم توليد/تحديث خطة المخاطر والمعالجة الداخلية '
                 '(%d جديدة، %d محدّثة). · Internal risks & remediation generated (%d new, %d updated).'
                 % (summary['created'], summary['updated'], summary['created'], summary['updated']))
    return redirect('risk:list')


@login_required
@company_portal_required
@require_http_methods(["POST"])
def task_set_status(request, task_id):
    """POST-only: update one remediation task's status (tenant-safe, audited)."""
    from .risk_engine import set_task_status
    company = request.user.company
    task = services.get_company_task(company, task_id)
    if task is None:
        messages.error(request, 'المهمة غير موجودة أو لا تخصّ شركتك.')
        return redirect('risk:list')
    try:
        set_task_status(company, task, request.POST.get('status', ''), actor=request.user)
        messages.success(request, 'تم تحديث حالة المعالجة · Remediation status updated.')
    except ValueError:
        messages.error(request, 'حالة غير صالحة · Invalid status.')
    return redirect('risk:detail', risk_id=task.risk_id)


def _linked_objects(request, company):
    """Resolve optional source FKs from GET params, tenant-validated. Returns a dict of kwargs."""
    from compliance.models import ControlAssessment, EvidenceAnalysisResult
    kw, prefill = {}, ''
    aid = request.GET.get('assessment_id')
    if aid:
        a = ControlAssessment.objects.filter(id=aid, company=company).select_related('control').first()
        if a:
            kw['control_assessment'] = a
            kw['control'] = a.control
            kw['framework_version'] = a.control.framework_version
            kw['source'] = 'control_assessment'
            prefill = f'خطر من تقييم الضابط {a.control.control_id}'
    nid = request.GET.get('analysis_id')
    if nid:
        n = EvidenceAnalysisResult.objects.filter(id=nid, company=company).select_related('control').first()
        if n:
            kw['evidence_analysis_result'] = n
            kw['control'] = n.control
            kw['source'] = 'evidence_analysis'
            prefill = 'خطر من نتيجة التحليل الاستشاري'
    if request.GET.get('source') == 'gap_analysis':
        kw['source'] = 'gap_analysis'
        prefill = request.GET.get('title', 'خطر من فجوة امتثال')
    return kw, prefill


@login_required
@require_http_methods(["GET", "POST"])
@company_portal_required
def risk_create(request):
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    linked, prefill = _linked_objects(request, company)
    if request.method == 'POST':
        form = RiskForm(request.POST)
        if form.is_valid():
            risk = form.save(commit=False)
            risk.company = company
            risk.created_by = request.user
            # Apply tenant-validated source links from the originating finding (POST-carried).
            post_linked, _ = _linked_objects(request, company)
            for k, v in post_linked.items():
                setattr(risk, k, v)
            risk.save()
            messages.success(request, 'تم حفظ الخطر.')
            return redirect('risk:detail', risk_id=risk.id)
    else:
        form = RiskForm(initial={'title': prefill} if prefill else None)
    return render(request, 'risk/risk_form.html', {
        'company': company, 'form': form, 'linked': linked, 'mode': 'create'})


@login_required
@require_http_methods(["GET", "POST"])
def risk_edit(request, risk_id):
    company = request.user.company
    risk = services.get_company_risk(company, risk_id)
    if risk is None:
        messages.error(request, 'الخطر غير موجود أو لا يخصّ شركتك.')
        return redirect('risk:list')
    if request.method == 'POST':
        form = RiskForm(request.POST, instance=risk)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث الخطر.')
            return redirect('risk:detail', risk_id=risk.id)
    else:
        form = RiskForm(instance=risk)
    return render(request, 'risk/risk_form.html', {
        'company': company, 'form': form, 'risk': risk, 'mode': 'edit'})


@login_required
@require_http_methods(["GET", "POST"])
def task_create(request, risk_id):
    company = request.user.company
    risk = services.get_company_risk(company, risk_id)
    if risk is None:
        messages.error(request, 'الخطر غير موجود أو لا يخصّ شركتك.')
        return redirect('risk:list')
    if request.method == 'POST':
        form = RemediationTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.company = company
            task.risk = risk
            task.created_by = request.user
            task.save()
            messages.success(request, 'تم إنشاء مهمة المعالجة.')
            return redirect('risk:detail', risk_id=risk.id)
    else:
        form = RemediationTaskForm()
    return render(request, 'risk/task_form.html', {
        'company': company, 'risk': risk, 'form': form, 'mode': 'create'})


@login_required
@require_http_methods(["GET", "POST"])
def task_edit(request, task_id):
    company = request.user.company
    task = services.get_company_task(company, task_id)
    if task is None:
        messages.error(request, 'المهمة غير موجودة أو لا تخصّ شركتك.')
        return redirect('risk:list')
    if request.method == 'POST':
        form = RemediationTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث مهمة المعالجة.')
            return redirect('risk:detail', risk_id=task.risk_id)
    else:
        form = RemediationTaskForm(instance=task)
    return render(request, 'risk/task_form.html', {
        'company': company, 'risk': task.risk, 'form': form, 'task': task, 'mode': 'edit'})


@login_required
def risk_auditor_view(request, assignment_id):
    """Read-only risk register for an auditor's accepted assignment (active auditor only)."""
    from auditors import services as auditor_services
    assignment = auditor_services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    if not auditor_services.auditor_can_view_company_context(assignment):
        messages.error(request, 'لا يمكن عرض بيانات الشركة قبل تفعيل الحساب وقبول الإسناد.')
        return redirect('auditors:dashboard')
    company = assignment.company
    return render(request, 'risk/risk_auditor_view.html', {
        'company': company, 'assignment': assignment,
        'risks': services.company_risks(company).select_related('control'),
        'counts': services.risk_dashboard_counts(company)})
