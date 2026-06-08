# Prompt 09 — AI Evidence Analyzer Repair

Repair AI Evidence Analyzer according to SRS FR-006.

Important:
AI does not issue final verdict.
AI produces an evidence analysis suggestion only.

Input:
- control requirements
- evidence requirements
- extracted text
- company context
- framework
- previous analysis if re-analysis

AI must return JSON:
{
  "suggested_status": "compliant|partially_compliant|non_compliant|insufficient_evidence",
  "confidence": 0-100,
  "reasoning_en": "...",
  "reasoning_ar": "...",
  "recommendations_en": "...",
  "recommendations_ar": "...",
  "missing_elements": [],
  "evidence_strength": "strong|medium|weak",
  "needs_human_review": true/false,
  "fabrication_or_template_risk": "low|medium|high"
}

Evaluation criteria:
- relevance
- completeness
- currency
- specificity
- implementation evidence
- not only generic policy wording

Operational requirements:
- Retry 3 times with exponential backoff.
- Timeout after 60 seconds.
- Rate limit API calls.
- Store raw request/response safely.
- Mask sensitive secrets from prompts.
- Batch analysis must be queued with Celery.

Acceptance criteria:
- AI result is stored separately from final status.
- Low confidence flags human review.
- OpenAI failure does not break user workflow.
- Tests use mocked AI responses.
