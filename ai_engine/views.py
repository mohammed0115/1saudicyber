"""
AI Engine Views - Classification, Gap Analysis APIs
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from .services import classify_company, generate_gap_analysis
from .models import AIClassificationLog, GapAnalysis
from core.roles import company_portal_required


@login_required
def run_classification(request):
    """Trigger AI classification for the user's company."""
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'No company associated'}, status=400)

    result = classify_company({
        'name': company.name,
        'sector': company.get_sector_display(),
        'size': company.get_size_display(),
        'target_aramco': company.target_aramco,
        'target_sabic': company.target_sabic,
        'target_nca': company.target_nca,
    })

    if 'error' not in result:
        company.risk_level = result.get('risk_level', 'medium')
        company.classification_summary = result.get('summary_en', '')
        company.classification_summary_ar = result.get('summary_ar', '')
        company.classification_date = timezone.now()
        company.status = 'classified'
        company.save()

        # Log classification
        AIClassificationLog.objects.create(
            company=company,
            input_data={
                'name': company.name,
                'sector': company.sector,
                'size': company.size,
                'targets': company.applicable_frameworks,
            },
            output_data=result,
            model_used=result.get('model_used', ''),
            prompt_tokens=result.get('prompt_tokens', 0),
            completion_tokens=result.get('completion_tokens', 0),
            processing_time_ms=result.get('processing_time_ms', 0),
        )

    return JsonResponse(result)


@login_required
@company_portal_required
def run_gap_analysis(request):
    """Phase 8D-2-FIX-A — safe, read-only advisory gap-analysis landing page.

    The previous implementation triggered a real AI/network call on GET and read a
    non-existent ``company.applicable_frameworks`` attribute, which returned HTTP 500.
    This view now renders a safe advisory page (no AI call, no network, no writes) and
    points users to the official, subscription-gated compliance reports. Advisory only —
    never a final compliance decision.
    """
    company = getattr(request.user, 'company', None)
    if not company:
        return render(request, 'dashboard/no_company.html')
    return render(request, 'ai_engine/gap_analysis_advisory.html', {'company': company})


@login_required
def classification_result(request):
    """View the AI classification result for the user's company."""
    company = request.user.company
    if not company:
        return redirect('dashboard:main')

    latest_log = AIClassificationLog.objects.filter(company=company).order_by('-created_at').first()

    context = {
        'company': company,
        'classification': latest_log.output_data if latest_log else {},
    }
    return render(request, 'compliance/classification_result.html', context)
