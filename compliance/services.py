"""
Compliance services — evidence processing pipeline.
Extracted from the view so it can run synchronously (dev) or via Celery (prod).

Reliability contract: this pipeline must ALWAYS drive an Evidence row to a terminal
status. It must never leave it stuck at 'processing'/'ai_analyzing' — a crash at any step
lands it on a terminal state with ai_verdict='error' so the UI shows "Analysis failed",
not an eternal spinner. Every step is guarded and every failure is logged.
"""
import logging

from django.utils import timezone

from ai_engine.services import process_uploaded_file, analyze_evidence
from ai_engine.models import AIAuditLog

logger = logging.getLogger(__name__)

# R3 — canonical source-of-truth boundaries (evidence v1/v2 coexist by UX path, NOT merged):
#   * Evidence           — control-detail upload; ADVISORY OCR/AI only. Never authoritative.
#   * EvidenceSubmission  — checklist upload; the HUMAN review file lifecycle (auditor verdict).
#   * ControlGapAssessment (gap_engine) — the derived compliance/gap status used in reports.
#   * AuditorFinalVerdict — the human final verdict.
# CompanyControl.status is a display roll-up; a human/compliance decision below must never be
# overwritten by the advisory AI path.
HUMAN_AUTHORITATIVE_STATUSES = {
    'compliant', 'non_compliant', 'partially_compliant', 'not_applicable',
}

# Terminal Evidence.status used when analysis finished (success OR handled failure). We
# reuse 'reviewed' (a valid model choice — no migration) and carry the failure signal in
# ai_verdict='error', which the template renders as a red "Analysis failed" badge.
_TERMINAL_STATUS = 'reviewed'


def _mark_evidence_error(evidence, exc):
    """Land a crashed Evidence on a terminal state so it never stays 'processing'."""
    try:
        evidence.status = _TERMINAL_STATUS
        evidence.ai_verdict = 'error'
        evidence.ai_reasoning = (f'Automated analysis failed: {exc}')[:2000]
        evidence.save(update_fields=['status', 'ai_verdict', 'ai_reasoning'])
    except Exception:  # pragma: no cover - last-resort guard
        logger.exception('Could not mark evidence %s as errored', getattr(evidence, 'id', '?'))


def process_evidence_pipeline(evidence_id):
    """Run OCR + AI analysis for one Evidence row and update all related records.

    Always returns a dict and always leaves the Evidence on a terminal status.
    """
    from compliance.models import Evidence
    try:
        evidence = Evidence.objects.select_related(
            'company_control', 'company_control__control', 'company_control__control__framework',
            'company_control__company',
        ).get(id=evidence_id)
    except Evidence.DoesNotExist:
        logger.warning('process_evidence_pipeline: evidence %s not found', evidence_id)
        return {'error': 'evidence not found'}

    try:
        cc = evidence.company_control
        control = cc.control
        company = cc.company

        # 1) OCR / text extraction. The extractors already swallow their own errors and
        # return empty text; guard here too in case of an unexpected raise (e.g. file.path).
        try:
            ocr = process_uploaded_file(evidence.file.path, evidence.file_type)
        except Exception as e:
            logger.exception('OCR step failed for evidence %s', evidence_id)
            ocr = {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}
        evidence.extracted_text = ocr.get('text', '')
        evidence.ocr_confidence = ocr.get('confidence', 0.0)
        evidence.ocr_language = ocr.get('language', '')
        evidence.status = 'ai_analyzing'
        evidence.save()

        if not evidence.extracted_text:
            # No text (e.g. OCR not installed) is NOT an error — it's insufficient evidence
            # awaiting human review. Terminal state, no spinner.
            evidence.status = _TERMINAL_STATUS
            evidence.save(update_fields=['status'])
            return {'verdict': 'insufficient_evidence', 'note': ocr.get('error') or 'no text extracted'}

        # 2) AI analysis. analyze_evidence already returns a safe dict (incl. missing API
        # key) rather than raising, but keep it inside the outer guard regardless.
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
        evidence.status = _TERMINAL_STATUS
        evidence.analyzed_at = timezone.now()
        evidence.save()

        cc.ai_verdict = ai.get('verdict', '')
        cc.ai_confidence = ai.get('confidence', 0.0)
        cc.ai_reasoning = ai.get('reasoning_en', '')
        cc.ai_reasoning_ar = ai.get('reasoning_ar', '')
        cc.ai_recommendations = '\n'.join(ai.get('recommendations_en', []))
        cc.ai_recommendations_ar = '\n'.join(ai.get('recommendations_ar', []))
        # R3 — single source of truth: advisory AI is NEVER authoritative. It may move a
        # control into the advisory 'ai_reviewed' state, but must NOT overwrite a status that
        # reflects a human/compliance decision (compliant/non_compliant/partial/not_applicable).
        if cc.status not in HUMAN_AUTHORITATIVE_STATUSES:
            cc.status = 'ai_reviewed'
        cc.last_assessed = timezone.now()
        cc.save()

        # The audit log is best-effort — its failure must not undo a completed analysis.
        try:
            AIAuditLog.objects.create(
                evidence_id=evidence.id, control_id=control.control_id, company_name=company.name,
                input_text=evidence.extracted_text[:2000], verdict=ai.get('verdict', ''),
                confidence=ai.get('confidence', 0.0), reasoning=ai.get('reasoning_en', ''),
                reasoning_ar=ai.get('reasoning_ar', ''),
                recommendations='\n'.join(ai.get('recommendations_en', [])),
                recommendations_ar='\n'.join(ai.get('recommendations_ar', [])),
                model_used=ai.get('model_used', ''), prompt_tokens=ai.get('prompt_tokens', 0),
                completion_tokens=ai.get('completion_tokens', 0),
                processing_time_ms=ai.get('processing_time_ms', 0),
            )
        except Exception:
            logger.exception('AIAuditLog write failed for evidence %s (analysis kept)', evidence_id)

        return {'verdict': cc.ai_verdict, 'confidence': cc.ai_confidence}
    except Exception as e:
        logger.exception('Evidence pipeline crashed for %s', evidence_id)
        _mark_evidence_error(evidence, e)
        return {'error': str(e)}
