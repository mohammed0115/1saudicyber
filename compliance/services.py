"""Evidence processing with explicit, recoverable state transitions."""
from django.utils import timezone

from ai_engine.models import AIAuditLog
from ai_engine.services import analyze_evidence, process_uploaded_file, validate_evidence_analysis
from compliance.file_validation import validate_stored_evidence


def _fail_evidence(evidence, message):
    evidence.status = 'failed'
    evidence.processing_error = str(message)[:4000]
    evidence.save(update_fields=['status', 'processing_error'])
    return {'error': evidence.processing_error, 'status': evidence.status}


def _mark_manual_review(evidence, message):
    evidence.status = 'needs_manual_review'
    evidence.processing_error = str(message)[:4000]
    evidence.analyzed_at = timezone.now()
    evidence.save(update_fields=['status', 'processing_error', 'analyzed_at'])
    return {'verdict': 'insufficient_evidence', 'status': evidence.status}


def process_evidence_pipeline(evidence_id):
    """Run validation, extraction and AI analysis for one Evidence record.

    A failed extraction or model response never marks the evidence/underlying
    control as reviewed. Those cases are surfaced for a human reviewer instead.
    """
    from compliance.models import Evidence

    try:
        evidence = Evidence.objects.select_related(
            'company_control', 'company_control__control', 'company_control__control__framework',
            'company_control__company',
        ).get(id=evidence_id)
    except Evidence.DoesNotExist:
        return {'error': 'evidence not found'}

    try:
        evidence.processing_attempts += 1
        evidence.status = 'processing'
        evidence.processing_error = ''
        evidence.save(update_fields=['processing_attempts', 'status', 'processing_error'])

        validate_stored_evidence(evidence.file.path)
        ocr = process_uploaded_file(evidence.file.path, evidence.file_type)
        evidence.extracted_text = ocr.get('text', '')
        evidence.ocr_confidence = ocr.get('confidence', 0.0)
        evidence.ocr_language = ocr.get('language', '')
        evidence.save(update_fields=['extracted_text', 'ocr_confidence', 'ocr_language'])

        if not evidence.extracted_text.strip():
            return _mark_manual_review(
                evidence, ocr.get('error') or 'No readable text was extracted from the evidence.'
            )

        control = evidence.company_control.control
        evidence.status = 'ai_analyzing'
        evidence.save(update_fields=['status'])
        ai = analyze_evidence(evidence.extracted_text, {
            'control_id': control.control_id,
            'framework': control.framework.code,
            'title': control.title,
            'description': control.description,
            'evidence_type': control.evidence_type,
        })
        if ai.get('error'):
            return _fail_evidence(evidence, ai['error'])
        ai = validate_evidence_analysis(ai)

        evidence.ai_analysis = ai
        evidence.ai_verdict = ai['verdict']
        evidence.ai_reasoning = ai['reasoning_en']
        evidence.ai_reasoning_ar = ai['reasoning_ar']
        evidence.analyzed_at = timezone.now()

        if ai['verdict'] == 'insufficient_evidence':
            evidence.status = 'needs_manual_review'
            evidence.processing_error = 'The AI response requires a human reviewer.'
            evidence.save()
            return {'verdict': ai['verdict'], 'status': evidence.status}

        evidence.status = 'reviewed'
        evidence.processing_error = ''
        evidence.save()

        company_control = evidence.company_control
        company_control.ai_verdict = ai['verdict']
        company_control.ai_confidence = ai['confidence']
        company_control.ai_reasoning = ai['reasoning_en']
        company_control.ai_reasoning_ar = ai['reasoning_ar']
        company_control.ai_recommendations = '\n'.join(ai['recommendations_en'])
        company_control.ai_recommendations_ar = '\n'.join(ai['recommendations_ar'])
        company_control.status = 'ai_reviewed'
        company_control.last_assessed = timezone.now()
        company_control.save()

        AIAuditLog.objects.create(
            evidence_id=evidence.id, control_id=control.control_id,
            company_name=company_control.company.name, input_text=evidence.extracted_text[:2000],
            verdict=ai['verdict'], confidence=ai['confidence'],
            reasoning=ai['reasoning_en'], reasoning_ar=ai['reasoning_ar'],
            recommendations='\n'.join(ai['recommendations_en']),
            recommendations_ar='\n'.join(ai['recommendations_ar']),
            model_used=ai.get('model_used', ''), prompt_tokens=ai.get('prompt_tokens', 0),
            completion_tokens=ai.get('completion_tokens', 0),
            processing_time_ms=ai.get('processing_time_ms', 0),
        )
        return {'verdict': company_control.ai_verdict, 'confidence': company_control.ai_confidence, 'status': evidence.status}
    except Exception as exc:
        return _fail_evidence(evidence, exc)
