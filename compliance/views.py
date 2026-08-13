"""
Compliance Views - Controls listing, Evidence upload, AI Analysis
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .file_validation import validate_evidence_upload
from .models import CompanyControl, Control, Domain, Evidence, Framework


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
        'allowed_evidence_accept': ','.join(
            f'.{extension}' for extension in settings.ALLOWED_EVIDENCE_EXTENSIONS
        ),
        'max_evidence_file_size_mb': settings.MAX_EVIDENCE_FILE_SIZE // (1024 * 1024),
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

    try:
        file_ext = validate_evidence_upload(uploaded_file)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('compliance:control_detail', control_id=control_id)

    evidence = Evidence.objects.create(
        company_control=company_control,
        uploaded_by=request.user,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        file_type=file_ext,
        file_size=uploaded_file.size,
        status='queued' if settings.EVIDENCE_ASYNC_ENABLED else 'processing',
    )

    from compliance.services import process_evidence_pipeline
    if settings.EVIDENCE_ASYNC_ENABLED:
        try:
            from monitoring.tasks import analyze_evidence_async
            task = analyze_evidence_async.delay(evidence.id)
            evidence.task_id = task.id or ''
            evidence.save(update_fields=['task_id'])
            messages.success(request, 'Evidence uploaded and queued for secure background analysis.')
        except Exception:
            # A broker outage must not leave the evidence permanently queued.
            result = process_evidence_pipeline(evidence.id)
            if result.get('error'):
                messages.error(request, 'Evidence was saved, but processing failed and requires review.')
            else:
                messages.success(request, 'Evidence uploaded and processed using the recovery path.')
    else:
        result = process_evidence_pipeline(evidence.id)
        if result.get('error'):
            messages.error(request, 'Evidence was saved, but processing failed and requires review.')
        elif result.get('status') == 'needs_manual_review':
            messages.warning(request, 'Evidence was saved and requires human review before an AI verdict can be used.')
        else:
            messages.success(request, 'Evidence uploaded and analyzed successfully.')

    return redirect('compliance:control_detail', control_id=control_id)
