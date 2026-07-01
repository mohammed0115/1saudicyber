"""
Monitoring Views - Continuous compliance hub, alerts, reports
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import ComplianceScore, Alert, MonthlyReport, CertificateTracker
from core.roles import company_portal_required


@login_required
@company_portal_required
def compliance_hub(request):
    """Phase 10: Continuous Compliance Hub - daily scores, monthly reports, renewal countdown."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Score history (last 30 days)
    scores = ComplianceScore.objects.filter(company=company).order_by('-date')[:30]

    # Monthly reports
    reports = MonthlyReport.objects.filter(company=company).order_by('-month')[:12]

    # Certificate trackers
    certificates = CertificateTracker.objects.filter(company=company)

    # Active alerts
    alerts = Alert.objects.filter(company=company, is_resolved=False).order_by('-created_at')[:20]

    context = {
        'company': company,
        'scores': scores,
        'reports': reports,
        'certificates': certificates,
        'alerts': alerts,
        'unresolved_alerts': alerts.count(),
    }
    return render(request, 'monitoring/compliance_hub.html', context)


@login_required
@company_portal_required
def realtime_monitoring(request):
    """Real-time monitoring dashboard - live event feed."""
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')

    # Compute severity counts from the unsliced queryset; filtering a sliced
    # queryset raises "Cannot filter a query once a slice has been taken."
    company_alerts = Alert.objects.filter(company=company)
    alerts = company_alerts.order_by('-created_at')[:50]

    context = {
        'company': company,
        'alerts': alerts,
        'critical': company_alerts.filter(severity='critical').count(),
        'high': company_alerts.filter(severity='high').count(),
        'medium': company_alerts.filter(severity='medium').count(),
    }
    return render(request, 'monitoring/realtime.html', context)


@login_required
def score_api(request):
    """API endpoint for score chart data."""
    company = request.user.company
    scores = ComplianceScore.objects.filter(company=company).order_by('date')[:30]
    data = [{
        'date': s.date.isoformat(),
        'overall': s.overall_score,
        'nca': s.nca_score,
        'aramco': s.aramco_score,
        'sabic': s.sabic_score,
    } for s in scores]
    return JsonResponse({'scores': data})


@login_required
def event_stream(request):
    """
    Server-Sent Events feed for the real-time dashboard (FR-010 / Prototype Phase 10B).
    Works under WSGI/Gunicorn without WebSocket infrastructure; clients consume via EventSource.
    Streams unresolved alerts as they appear, then keep-alives.
    """
    import json
    import time
    from django.http import StreamingHttpResponse

    company = request.user.company

    def gen():
        last_id = 0
        # Prime with the latest known alert id so we only stream new ones.
        latest = Alert.objects.filter(company=company).order_by('-id').first()
        last_id = latest.id if latest else 0
        ticks = 0
        while ticks < 600:  # ~10 min cap per connection; client auto-reconnects
            new_alerts = Alert.objects.filter(company=company, id__gt=last_id).order_by('id')
            for a in new_alerts:
                last_id = a.id
                payload = {
                    'id': a.id, 'type': a.get_alert_type_display(),
                    'severity': a.severity, 'title': a.title,
                    'created_at': a.created_at.isoformat(),
                }
                yield f"event: alert\ndata: {json.dumps(payload)}\n\n"
            yield ": keep-alive\n\n"
            ticks += 1
            time.sleep(1)

    resp = StreamingHttpResponse(gen(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


# ============================================================
# Phase 5B — Continuous Monitoring Foundation (read-only surfaces)
# ============================================================
@login_required
@company_portal_required
def monitoring_overview(request):
    """Company-scoped continuous-monitoring dashboard (counters)."""
    from .continuous import summarize_company_monitoring
    from .models import MonitoringCheck, MonitoringFinding
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    from compliance.journey import build_page_guide
    return render(request, 'monitoring/overview.html', {
        'company': company,
        'summary': summarize_company_monitoring(company),
        'checks': MonitoringCheck.objects.filter(company=company).select_related('control')[:50],
        'findings': MonitoringFinding.objects.filter(
            company=company).select_related('monitoring_run')[:50],
        'guide': build_page_guide(company, 'monitoring'),
    })


@login_required
@company_portal_required
def checks_list(request):
    from .models import MonitoringCheck
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'monitoring/checks_list.html', {
        'company': company,
        'checks': MonitoringCheck.objects.filter(company=company).select_related(
            'control', 'framework_version')})


@login_required
@company_portal_required
def findings_list(request):
    from .models import MonitoringFinding
    company = request.user.company
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'monitoring/findings_list.html', {
        'company': company,
        'findings': MonitoringFinding.objects.filter(company=company).select_related('monitoring_run')})


@login_required
def auditor_monitoring_view(request, assignment_id):
    """Read-only monitoring summary for an auditor's accepted assignment (active auditor only)."""
    from auditors import services as auditor_services
    from .continuous import summarize_company_monitoring
    from .models import MonitoringFinding
    from django.contrib import messages
    assignment = auditor_services.get_assignment_for_user(request.user, assignment_id)
    if assignment is None:
        messages.error(request, 'الطلب غير موجود أو لا يخصّك.')
        return redirect('auditors:dashboard')
    if not auditor_services.auditor_can_view_company_context(assignment):
        messages.error(request, 'لا يمكن عرض بيانات الشركة قبل تفعيل الحساب وقبول الإسناد.')
        return redirect('auditors:dashboard')
    company = assignment.company
    return render(request, 'monitoring/auditor_view.html', {
        'company': company, 'assignment': assignment,
        'summary': summarize_company_monitoring(company),
        'findings': MonitoringFinding.objects.filter(company=company)[:50]})
