"""
Auditor Portal Views - Review evidence, add notes, submit reports
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from compliance.models import Assessment, CompanyControl, Evidence
from .models import AuditorNote, DocumentRequest, AuditReport


def auditor_required(view_func):
    """Decorator to ensure user is an auditor."""
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'auditor':
            messages.error(request, 'Access denied. Auditor role required.')
            return redirect('dashboard:main')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@auditor_required
def auditor_dashboard(request):
    """Auditor main dashboard - assigned assessments."""
    assessments = Assessment.objects.filter(
        assigned_auditor=request.user
    ).select_related('company').order_by('-created_at')

    context = {
        'assessments': assessments,
        'pending': assessments.filter(status='auditor_review').count(),
        'completed': assessments.filter(status='completed').count(),
    }
    return render(request, 'auditor_portal/dashboard.html', context)


@login_required
@auditor_required
def review_assessment(request, assessment_id):
    """Review a specific assessment - view all controls and evidence."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_controls = CompanyControl.objects.filter(
        company=assessment.company
    ).select_related('control', 'control__framework', 'control__domain').order_by('control__domain__order', 'control__control_id')

    context = {
        'assessment': assessment,
        'company_controls': company_controls,
        'notes': AuditorNote.objects.filter(assessment=assessment),
        'document_requests': DocumentRequest.objects.filter(assessment=assessment),
    }
    return render(request, 'auditor_portal/review_assessment.html', context)


@login_required
@auditor_required
def review_control(request, assessment_id, control_id):
    """Review a specific control's evidence."""
    assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
    company_control = get_object_or_404(CompanyControl, id=control_id, company=assessment.company)
    evidences = Evidence.objects.filter(company_control=company_control).order_by('-uploaded_at')

    context = {
        'assessment': assessment,
        'company_control': company_control,
        'evidences': evidences,
        'notes': AuditorNote.objects.filter(assessment=assessment, company_control=company_control),
    }
    return render(request, 'auditor_portal/review_control.html', context)


@login_required
@auditor_required
def add_note(request, assessment_id, control_id):
    """Add auditor note to a control."""
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
        company_control = get_object_or_404(CompanyControl, id=control_id)

        AuditorNote.objects.create(
            assessment=assessment,
            company_control=company_control,
            auditor=request.user,
            note=request.POST.get('note', ''),
            is_finding=request.POST.get('is_finding') == 'on',
            requires_action=request.POST.get('requires_action') == 'on',
        )
        messages.success(request, 'Note added successfully.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
def request_document(request, assessment_id, control_id):
    """Request additional document from company."""
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)
        company_control = get_object_or_404(CompanyControl, id=control_id)

        DocumentRequest.objects.create(
            assessment=assessment,
            company_control=company_control,
            auditor=request.user,
            description=request.POST.get('description', ''),
            description_ar=request.POST.get('description_ar', ''),
        )
        messages.success(request, 'Document request sent to company.')
    return redirect('auditor_portal:review_control', assessment_id=assessment_id, control_id=control_id)


@login_required
@auditor_required
def submit_report(request, assessment_id):
    """Submit final audit report."""
    if request.method == 'POST':
        assessment = get_object_or_404(Assessment, id=assessment_id, assigned_auditor=request.user)

        AuditReport.objects.create(
            assessment=assessment,
            auditor=request.user,
            verdict=request.POST.get('verdict', 'fail'),
            executive_summary=request.POST.get('executive_summary', ''),
            executive_summary_ar=request.POST.get('executive_summary_ar', ''),
        )

        assessment.status = 'completed'
        assessment.save()

        # UC-004 step 11: issue a certificate on a passing/conditional verdict.
        verdict = request.POST.get('verdict', 'fail')
        if verdict in ('pass', 'conditional_pass'):
            from datetime import timedelta
            from django.utils import timezone
            from monitoring.models import CertificateTracker
            company = assessment.company
            today = timezone.localdate()
            expiry = today + timedelta(days=365)
            for fw in assessment.frameworks.all():
                cert_no = f'CT-{company.cr_number}-{fw.code}-{today:%Y%m%d}'
                CertificateTracker.objects.update_or_create(
                    company=company, framework_code=fw.code,
                    defaults={'certificate_number': cert_no, 'issued_date': today,
                              'expiry_date': expiry, 'days_remaining': 365, 'is_active': True},
                )
            company.status = 'certified'
            company.save(update_fields=['status'])

        messages.success(request, 'Audit report submitted successfully.')
        return redirect('auditor_portal:dashboard')

    return redirect('auditor_portal:review_assessment', assessment_id=assessment_id)
