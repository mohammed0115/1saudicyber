"""
AI Engine Views - Classification, Gap Analysis APIs
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .services import classify_company, generate_gap_analysis
from .models import AIClassificationLog, GapAnalysis
from compliance.models import CompanyControl, Framework


@login_required
@require_POST
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
@require_POST
def run_gap_analysis(request):
    """Trigger AI gap analysis for the user's company."""
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'No company associated'}, status=400)

    # Gather current control statuses
    controls_status = list(
        CompanyControl.objects.filter(company=company).values(
            'control__control_id', 'control__title', 'control__framework__code',
            'control__domain__name', 'status', 'ai_verdict', 'ai_confidence'
        )
    )

    result = generate_gap_analysis(
        {
            'name': company.name,
            'sector': company.get_sector_display(),
            'size': company.get_size_display(),
            'frameworks': company.applicable_frameworks,
        },
        controls_status
    )

    if 'error' not in result:
        # Persist one GapAnalysis row per targeted framework (was: NCA only — bug).
        targeted = []
        if company.target_nca:
            targeted.append('NCA_ECC')
        if company.target_aramco:
            targeted.append('ARAMCO_SACS002')
        if company.target_sabic:
            targeted.append('SABIC_CT')

        for fw_code in targeted:
            fw_controls = CompanyControl.objects.filter(
                company=company, control__framework__code=fw_code
            )
            total = fw_controls.count()
            compliant = fw_controls.filter(status='compliant').count()
            non_compliant = fw_controls.filter(status='non_compliant').count()
            partial = fw_controls.filter(status='partially_compliant').count()
            not_assessed = fw_controls.filter(
                status__in=['not_started', 'in_progress', 'evidence_uploaded']
            ).count()
            fw_score = (compliant / total * 100) if total else result.get('compliance_score', 0)

            GapAnalysis.objects.create(
                company=company,
                framework_code=fw_code,
                total_controls=total,
                compliant_count=compliant,
                non_compliant_count=non_compliant,
                partially_compliant_count=partial,
                not_assessed_count=not_assessed,
                compliance_score=fw_score,
                risk_score=result.get('overall_risk_score', 0),
                high_risk_gaps=result.get('critical_gaps', []),
                remediation_priorities=result.get('top_priorities_en', []),
                ai_prediction=result.get('predicted_audit_outcome_en', ''),
                ai_prediction_ar=result.get('predicted_audit_outcome_ar', ''),
            )

        # The overall score is deterministic and covers every applicable control;
        # the model's score remains advisory only in the stored analysis response.
        all_controls = CompanyControl.objects.filter(company=company)
        all_total = all_controls.count()
        all_compliant = all_controls.filter(status='compliant').count()
        deterministic_score = (all_compliant / all_total * 100) if all_total else 0.0
        result['advisory_compliance_score'] = result.get('compliance_score', 0)
        result['compliance_score'] = deterministic_score
        company.overall_compliance_score = deterministic_score
        company.save(update_fields=['overall_compliance_score'])

    return JsonResponse(result)


@login_required
def classification_result(request):
    """View the AI classification result for the user's company."""
    company = request.user.company
    if not company:
        return redirect('dashboard:main')

    latest_log = AIClassificationLog.objects.filter(company=company).order_by('-created_at').first()

    classification = latest_log.output_data if latest_log else {}
    framework_codes = []
    if company.target_nca:
        framework_codes.append('NCA_ECC')
    if company.target_aramco:
        framework_codes.append('ARAMCO_SACS002')
    if company.target_sabic:
        framework_codes.append('SABIC_CT')
    applicable_frameworks = Framework.objects.filter(code__in=framework_codes)
    for framework in applicable_frameworks:
        framework.control_count = framework.controls.count()

    context = {
        'company': company,
        'classification': classification,
        'applicable_frameworks': applicable_frameworks,
        'classification_reasoning': classification.get('summary_en', ''),
    }
    return render(request, 'compliance/classification_result.html', context)
