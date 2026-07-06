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
    """Compliance Officer Dashboard - Full control checklist, audit readiness."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # All company controls with status
    company_controls = CompanyControl.objects.filter(company=company).select_related('control', 'control__framework', 'control__domain')

    # Status breakdown
    status_counts = company_controls.values('status').annotate(count=Count('id'))

    # Framework-specific scores
    frameworks = Framework.objects.filter(is_active=True)
    framework_scores = {}
    for fw in frameworks:
        fw_controls = company_controls.filter(control__framework=fw)
        total = fw_controls.count()
        compliant = fw_controls.filter(status='compliant').count()
        framework_scores[fw.code] = {
            'name': fw.name,
            'total': total,
            'compliant': compliant,
            'score': (compliant / total * 100) if total > 0 else 0,
        }

    # Recent assessments
    assessments = Assessment.objects.filter(company=company).order_by('-created_at')[:5]

    # Pending evidence
    pending_controls = company_controls.filter(status__in=['not_started', 'in_progress'])

    context = {
        'company': company,
        'company_controls': company_controls,
        'status_counts': {item['status']: item['count'] for item in status_counts},
        'framework_scores': framework_scores,
        'assessments': assessments,
        'pending_controls': pending_controls[:20],
        'total_controls': company_controls.count(),
        'compliant_controls': company_controls.filter(status='compliant').count(),
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
