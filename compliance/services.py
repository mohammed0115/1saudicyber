"""
Compliance services — evidence processing pipeline.
Extracted from the view so it can run synchronously (dev) or via Celery (prod).
"""
from django.utils import timezone

from ai_engine.services import process_uploaded_file, analyze_evidence
from ai_engine.models import AIAuditLog


def process_evidence_pipeline(evidence_id):
    """Run OCR + AI analysis for one Evidence row and update all related records."""
    from compliance.models import Evidence
    try:
        evidence = Evidence.objects.select_related(
            'company_control', 'company_control__control', 'company_control__control__framework',
            'company_control__company',
        ).get(id=evidence_id)
    except Evidence.DoesNotExist:
        return {'error': 'evidence not found'}

    cc = evidence.company_control
    control = cc.control
    company = cc.company

    # 1) OCR / text extraction
    ocr = process_uploaded_file(evidence.file.path, evidence.file_type)
    evidence.extracted_text = ocr.get('text', '')
    evidence.ocr_confidence = ocr.get('confidence', 0.0)
    evidence.ocr_language = ocr.get('language', '')
    evidence.status = 'ai_analyzing'
    evidence.save()

    if not evidence.extracted_text:
        evidence.status = 'reviewed'
        evidence.save()
        return {'verdict': 'insufficient_evidence', 'note': 'no text extracted'}

    # 2) AI analysis
    ai = analyze_evidence(evidence.extracted_text, {
        'control_id': control.control_id,
        'framework': control.framework.code,
        'title': control.title,
        'description': control.description,
        'evidence_type': control.evidence_type,
    })

    evidence.ai_analysis = ai
    evidence.ai_verdict = ai.get('verdict', 'insufficient_evidence')
    evidence.ai_reasoning = ai.get('reasoning_en', '')
    evidence.ai_reasoning_ar = ai.get('reasoning_ar', '')
    evidence.status = 'reviewed'
    evidence.analyzed_at = timezone.now()
    evidence.save()

    cc.ai_verdict = ai.get('verdict', '')
    cc.ai_confidence = ai.get('confidence', 0.0)
    cc.ai_reasoning = ai.get('reasoning_en', '')
    cc.ai_reasoning_ar = ai.get('reasoning_ar', '')
    cc.ai_recommendations = '\n'.join(ai.get('recommendations_en', []))
    cc.ai_recommendations_ar = '\n'.join(ai.get('recommendations_ar', []))
    cc.status = 'ai_reviewed'
    cc.last_assessed = timezone.now()
    cc.save()

    AIAuditLog.objects.create(
        evidence_id=evidence.id, control_id=control.control_id, company_name=company.name,
        input_text=evidence.extracted_text[:2000], verdict=ai.get('verdict', ''),
        confidence=ai.get('confidence', 0.0), reasoning=ai.get('reasoning_en', ''),
        reasoning_ar=ai.get('reasoning_ar', ''),
        recommendations='\n'.join(ai.get('recommendations_en', [])),
        recommendations_ar='\n'.join(ai.get('recommendations_ar', [])),
        model_used=ai.get('model_used', ''), prompt_tokens=ai.get('prompt_tokens', 0),
        completion_tokens=ai.get('completion_tokens', 0), processing_time_ms=ai.get('processing_time_ms', 0),
    )
    return {'verdict': cc.ai_verdict, 'confidence': cc.ai_confidence}
