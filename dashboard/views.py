"""
Dashboard Views - Role-specific dashboards
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from core.models import Company
from compliance.models import CompanyControl, Assessment, Framework
from monitoring.models import ComplianceScore, Alert, CertificateTracker
from ai_engine.models import GapAnalysis
from core.roles import company_portal_required


@login_required
def main_dashboard(request):
    """Route to the correct portal based on the user's role (fail-closed).

    Phase 8D-3C: Get Solution staff/superuser go to the CRM console (never the
    customer compliance dashboard), and auditor accounts go to the auditor portal.
    """
    from core.roles import is_platform_admin_user
    # Get Solution staff/admin are NOT customers — send them to the CRM console.
    if is_platform_admin_user(request.user):
        return redirect('platform_admin:dashboard')
    role = request.user.role
    if role == 'executive':
        return executive_dashboard(request)
    elif role == 'auditor':
        return redirect('auditor_portal:dashboard')
    elif role == 'it_security':
        return it_security_dashboard(request)
    elif role == 'bu_manager':
        return bu_manager_dashboard(request)
    else:
        return compliance_officer_dashboard(request)


@login_required
@company_portal_required
def executive_dashboard(request):
    """Executive Leadership Dashboard - Risk heatmap, ROI, board reports."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Compliance scores
    scores = ComplianceScore.objects.filter(company=company).order_by('-date')[:30]

    # Alerts summary
    alerts = Alert.objects.filter(company=company, is_resolved=False)
    critical_alerts = alerts.filter(severity='critical').count()
    high_alerts = alerts.filter(severity='high').count()

    # Control status summary
    controls_summary = CompanyControl.objects.filter(company=company).values('status').annotate(count=Count('id'))

    # Gap analysis
    latest_gap = GapAnalysis.objects.filter(company=company).order_by('-generated_at').first()

    context = {
        'company': company,
        'scores': scores,
        'critical_alerts': critical_alerts,
        'high_alerts': high_alerts,
        'controls_summary': controls_summary,
        'latest_gap': latest_gap,
        'certificates': CertificateTracker.objects.filter(company=company),
    }
    return render(request, 'dashboard/executive.html', context)


@login_required
@company_portal_required
def compliance_officer_dashboard(request):
    """Compliance Officer Dashboard.

    Driven strictly by the company's APPROVED framework scope and its GENERATED control plan
    (ControlApplicabilityResult) — never by all active/legacy Framework rows. Fail-closed states:
      * no approved scope  -> ask the user to review & approve the framework scope.
      * approved, no plan   -> ask to generate the control plan.
      * plan exists         -> real counts + only approved frameworks that have generated controls.
    All queries are scoped to request.user.company (tenant isolation).
    """
    from compliance.models import CompanyFrameworkScope, ControlApplicabilityResult

    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    approved_scopes = list(CompanyFrameworkScope.objects
                           .filter(company=company, status='approved')
                           .select_related('framework_version', 'framework_version__framework'))
    has_approved_scope = bool(approved_scopes)

    # The generated control plan = applicable planned controls for this company only.
    plan = list(ControlApplicabilityResult.objects
                .filter(company=company, decision='applicable')
                .select_related('control', 'control__framework_version', 'control__domain'))
    total_controls = len(plan)
    has_control_plan = total_controls > 0

    # Progress status comes from CompanyControl (keyed by Control pk); planned-but-untracked
    # controls count as not-started. Everything is scoped to the plan, never to legacy imports.
    cc_status = dict(CompanyControl.objects.filter(company=company)
                     .values_list('control_id', 'status'))
    status_counts = {'not_started': 0, 'in_progress': 0, 'compliant': 0}
    for r in plan:
        st = cc_status.get(r.control_id, 'not_started')
        status_counts[st] = status_counts.get(st, 0) + 1
    compliant_controls = status_counts.get('compliant', 0)

    # Framework cards: only approved frameworks that actually have generated controls (no 0/0).
    framework_scores = {}
    if has_control_plan:
        for scope in approved_scopes:
            fv = scope.framework_version
            fv_plan = [r for r in plan if r.control.framework_version_id == fv.id]
            total = len(fv_plan)
            if total == 0:
                continue
            compliant = sum(1 for r in fv_plan if cc_status.get(r.control_id) == 'compliant')
            framework_scores[fv.code] = {
                'name': fv.display_name_ar,
                'total': total,
                'compliant': compliant,
                'score': (compliant / total * 100) if total > 0 else 0,
            }

    # Pending controls (need action) — from the plan, not legacy imports.
    pending_controls = [r for r in plan
                        if cc_status.get(r.control_id, 'not_started') in ('not_started', 'in_progress')][:20]

    from compliance.workflow_stepper import build_company_workflow_stepper
    context = {
        'company': company,
        'has_approved_scope': has_approved_scope,
        'has_control_plan': has_control_plan,
        'status_counts': status_counts,
        'framework_scores': framework_scores,
        'pending_controls': pending_controls,
        'total_controls': total_controls,
        'compliant_controls': compliant_controls,
        'stepper': build_company_workflow_stepper(company),
    }
    return render(request, 'dashboard/compliance_officer.html', context)


@login_required
@company_portal_required
def it_security_dashboard(request):
    """IT/Security Team Dashboard - Technical controls, vulnerabilities."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Technical controls (Access Control, Network Security, etc.)
    technical_domains = ['Access Control', 'Network Security', 'Data Protection', 'Cryptography', 'System Security']
    technical_controls = CompanyControl.objects.filter(
        company=company,
        control__domain__name__in=technical_domains
    ).select_related('control', 'control__domain')

    # Recent alerts. NOTE: count BEFORE slicing — filtering a sliced queryset raises
    # "Cannot filter a query once a slice has been taken" (a guaranteed 500).
    company_alerts = Alert.objects.filter(company=company)
    critical_count = company_alerts.filter(severity='critical').count()
    alerts = company_alerts.order_by('-created_at')[:20]

    context = {
        'company': company,
        'technical_controls': technical_controls,
        'alerts': alerts,
        'critical_count': critical_count,
    }
    return render(request, 'dashboard/it_security.html', context)


@login_required
@company_portal_required
def bu_manager_dashboard(request):
    """Business Unit Manager Dashboard - Department compliance, training."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Department-level compliance
    company_controls = CompanyControl.objects.filter(company=company).select_related('control__domain')
    domain_stats = company_controls.values('control__domain__name').annotate(
        total=Count('id'),
        compliant=Count('id', filter=Q(status='compliant')),
    )

    context = {
        'company': company,
        'domain_stats': domain_stats,
    }
    return render(request, 'dashboard/bu_manager.html', context)


@login_required
def gap_report_pdf(request):
    """Download the gap-analysis PDF (FR-007.12 / FR-011)."""
    from django.http import HttpResponse
    from dashboard.reports import gap_analysis_pdf
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    pdf = gap_analysis_pdf(company)
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="gap_analysis_{company.cr_number}.pdf"'
    return resp


@login_required
def compliance_export_xlsx(request):
    """Download the controls Excel export (FR-011.9 / FR-004.7)."""
    from django.http import HttpResponse
    from dashboard.reports import compliance_excel
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    data = compliance_excel(company)
    resp = HttpResponse(
        data, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="controls_{company.cr_number}.xlsx"'
    return resp
