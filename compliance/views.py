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
