"""Grounding, output validation, and governance records for AI-assisted evidence review."""
from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.db import transaction

from ai_engine.models import AIDecisionRecord, EvidenceChunk, ModelProfile


VALID_VERDICTS = {'compliant', 'non_compliant', 'partially_compliant', 'insufficient_evidence'}
DEFAULT_REVIEW_CONFIDENCE = 0.75


def _hash(payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def chunk_evidence(evidence, *, chunk_size=1500):
    """Create idempotent, cited segments from extracted evidence text."""
    text = (evidence.extracted_text or '').strip()
    if not text:
        return []
    chunks = [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]
    with transaction.atomic():
        evidence.chunks.all().delete()
        records = [
            EvidenceChunk(
                evidence=evidence,
                chunk_index=index,
                text=value,
                content_hash=_hash(value),
            )
            for index, value in enumerate(chunks)
        ]
        EvidenceChunk.objects.bulk_create(records)
    return records


def grounded_context(evidence, *, max_chars=8000):
    """Build a bounded prompt context with explicit chunk citations."""
    records = list(evidence.chunks.all().order_by('chunk_index'))
    if not records:
        records = chunk_evidence(evidence)
    parts, cited_indexes, consumed = [], [], 0
    for chunk in records:
        label = f'[chunk:{chunk.chunk_index}]\n'
        remaining = max_chars - consumed - len(label)
        if remaining <= 0:
            break
        value = chunk.text[:remaining]
        parts.append(label + value)
        cited_indexes.append(chunk.chunk_index)
        consumed += len(label) + len(value)
    return '\n\n'.join(parts), cited_indexes


def validate_evidence_analysis(result):
    """Validate the narrow contract required before a model response can affect workflow."""
    errors = []
    verdict = result.get('verdict')
    confidence = result.get('confidence')
    if verdict not in VALID_VERDICTS:
        errors.append('verdict is missing or invalid')
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        errors.append('confidence is missing or invalid')
        confidence = 0.0
    if not 0.0 <= confidence <= 1.0:
        errors.append('confidence must be between 0 and 1')
    return errors, confidence


def active_model_profile():
    return ModelProfile.objects.filter(is_active=True).order_by('key').first()


def record_evidence_decision(evidence, analysis, *, policy_version_reference='', trace_id=None):
    """Write a tamper-evident governance record without retaining duplicate raw evidence text."""
    errors, confidence = validate_evidence_analysis(analysis)
    _, cited_indexes = grounded_context(evidence)
    profile = active_model_profile()
    threshold = (profile.configuration.get('review_confidence_threshold', DEFAULT_REVIEW_CONFIDENCE)
                 if profile else DEFAULT_REVIEW_CONFIDENCE)
    status = 'accepted' if not errors and confidence >= float(threshold) else 'review_required'
    if analysis.get('error'):
        status = 'error'
    company_control = evidence.company_control
    record = AIDecisionRecord.objects.create(
        evidence=evidence,
        company=company_control.company,
        control=company_control.control,
        model_profile=profile,
        model_name=analysis.get('model_used') or (profile.model_name if profile else settings.OPENAI_MODEL),
        prompt_key='evidence-audit',
        prompt_version='1.0',
        policy_version_reference=policy_version_reference,
        input_hash=_hash({
            'evidence_id': evidence.id,
            'chunk_hashes': list(evidence.chunks.values_list('content_hash', flat=True)),
            'control_id': company_control.control.control_id,
        }),
        output_payload=analysis,
        output_hash=_hash(analysis),
        cited_chunk_indexes=cited_indexes,
        confidence=confidence,
        status=status,
        trace_id=trace_id,
    )
    return record
