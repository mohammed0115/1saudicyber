"""
Phase 6D — advisory AI Evidence Analyzer (gated, mockable, advisory-only).

Analyzes the PERSISTED extracted text of an EvidenceSubmission and stores an
advisory EvidenceAIAnalysis. It helps a human auditor — it NEVER decides
compliance (no C/PC/NC, no Compliance/Noncompliance), never writes
ControlAssessment / CompanyControl / reports, and never runs the Rule Engine.

Safety:
* Gated on a successful EvidenceTextExtraction (status='extracted', char_count>0).
* Provider is an injectable abstraction; tests use a fake provider — NO real
  network calls in tests. If no provider/key is configured, the result is a safe
  'skipped' state (never a crash).
* The prompt never contains a file path or any secret; provider errors are caught
  and converted to a safe 'failed' result.
"""
import json

ALLOWED_RELEVANCE = ('high', 'medium', 'low', 'unclear')
MAX_PROMPT_TEXT_CHARS = 8000
MAX_SUMMARY_CHARS = 1500
MAX_LIST_ITEMS = 12
MAX_ITEM_CHARS = 240

ADVISORY_INSTRUCTION = (
    "You assist a human auditor reviewing cybersecurity compliance evidence. "
    "You are ADVISORY ONLY: you DO NOT decide compliance, you DO NOT mark anything "
    "compliant/non-compliant or C/PC/NC, you DO NOT accept or reject evidence, and "
    "you DO NOT issue any certification or final decision. The final decision belongs "
    "to a human auditor. Never invent evidence not present in the text."
)

RESPONSE_SHAPE = (
    '{"relevance":"high|medium|low|unclear","confidence":0,"summary":"...",'
    '"matched_signals":["..."],"missing_items":["..."],"recommendations":["..."]}'
)


class ProviderUnavailable(Exception):
    """Raised when no AI provider/key is configured — handled as a safe 'skipped'."""


class EvidenceAnalyzerProvider:
    """Provider abstraction. analyze(prompt) -> dict (parsed JSON)."""

    def analyze(self, prompt):  # pragma: no cover - interface
        raise NotImplementedError


class OpenAIEvidenceProvider(EvidenceAnalyzerProvider):
    """Default provider. Uses the configured OpenAI key; unavailable if none."""

    def analyze(self, prompt):
        from django.conf import settings
        key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        if not key:
            raise ProviderUnavailable('AI provider not configured.')
        from ai_engine.services import get_openai_client
        client = get_openai_client()
        resp = client.chat.completions.create(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o'),
            messages=[
                {'role': 'system', 'content': ADVISORY_INSTRUCTION},
                {'role': 'user', 'content': prompt},
            ],
            response_format={'type': 'json_object'},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)


def default_provider():
    """Patchable factory for the default provider (tests override this)."""
    return OpenAIEvidenceProvider()


def can_analyze_submission(submission):
    """Extraction gate. Returns (ok, reason_ar). No side effects."""
    ext = getattr(submission, 'text_extraction', None)
    if ext is None:
        return False, 'يجب استخراج نص قابل للقراءة من الدليل قبل تشغيل التحليل الاستشاري.'
    if ext.status != 'extracted' or ext.char_count <= 0 or not (ext.extracted_text or '').strip():
        return False, 'يجب استخراج نص قابل للقراءة من الدليل قبل تشغيل التحليل الاستشاري.'
    return True, ''


def _control_of(submission):
    try:
        return submission.checklist_item.evidence_requirement.control
    except Exception:
        return None


def build_prompt(submission, extraction):
    """Build an advisory-only prompt. Never includes a file path or secrets."""
    control = _control_of(submission)
    cid = getattr(control, 'control_id', '') if control else ''
    ctitle = (getattr(control, 'title_ar', '') or getattr(control, 'title', '')) if control else ''
    cdesc = (getattr(control, 'description_ar', '') or getattr(control, 'description', '')) if control else ''
    fv = getattr(control, 'framework_version', None) if control else None
    fcode = fv.code if fv is not None else (getattr(getattr(control, 'framework', None), 'code', '') if control else '')
    excerpt = (extraction.extracted_text or '')[:MAX_PROMPT_TEXT_CHARS]
    return (
        f"{ADVISORY_INSTRUCTION}\n\n"
        f"Control ID: {cid}\nControl title: {ctitle}\nControl description: {cdesc}\n"
        f"Framework: {fcode}\n\n"
        f"Extracted evidence text (excerpt):\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
        f"Assess only whether the evidence text appears RELEVANT to the control and what is "
        f"present vs missing. Do NOT decide compliance. Respond with ONLY a JSON object of this "
        f"exact shape (no prose):\n{RESPONSE_SHAPE}"
    )


def _clean_list(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_LIST_ITEMS]:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:MAX_ITEM_CHARS])
    return out


def _validate(raw):
    """Validate/clamp a provider response. Returns a clean dict, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    relevance = raw.get('relevance')
    if relevance not in ALLOWED_RELEVANCE:
        relevance = 'unclear'
    try:
        confidence = int(raw.get('confidence', 0))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    summary = raw.get('summary', '')
    if not isinstance(summary, str):
        summary = ''
    return {
        'relevance': relevance,
        'confidence': confidence,
        'summary': summary.strip()[:MAX_SUMMARY_CHARS],
        'matched_signals': _clean_list(raw.get('matched_signals')),
        'missing_items': _clean_list(raw.get('missing_items')),
        'recommendations': _clean_list(raw.get('recommendations')),
    }


def _sanitized_raw(data):
    """Store only the validated, capped keys — never long uncontrolled output."""
    return {k: data[k] for k in ('relevance', 'confidence', 'summary',
                                 'matched_signals', 'missing_items', 'recommendations')}


def _upsert(submission, **fields):
    from .models import EvidenceAIAnalysis
    obj, _ = EvidenceAIAnalysis.objects.update_or_create(submission=submission, defaults=fields)
    return obj


def analyze_submission_evidence(submission, provider=None, actor=None):
    """Run advisory analysis for a submission and persist one EvidenceAIAnalysis (upsert)."""
    ok, reason = can_analyze_submission(submission)
    if not ok:
        return _upsert(submission, status='skipped', relevance='', confidence=0, summary='',
                       matched_signals=[], missing_items=[], recommendations=[],
                       raw_response={}, error_message=reason)

    extraction = submission.text_extraction
    prompt = build_prompt(submission, extraction)
    provider = provider or default_provider()
    try:
        raw = provider.analyze(prompt)
    except ProviderUnavailable as e:
        return _upsert(submission, status='skipped', relevance='', confidence=0, summary='',
                       matched_signals=[], missing_items=[], recommendations=[],
                       raw_response={}, error_message=str(e))
    except Exception:
        return _upsert(submission, status='failed', relevance='', confidence=0, summary='',
                       matched_signals=[], missing_items=[], recommendations=[],
                       raw_response={}, error_message='تعذر تنفيذ التحليل الاستشاري بأمان.')

    data = _validate(raw)
    if data is None:
        return _upsert(submission, status='failed', relevance='', confidence=0, summary='',
                       matched_signals=[], missing_items=[], recommendations=[],
                       raw_response={}, error_message='استجابة التحليل غير صالحة.')

    return _upsert(submission, status='completed', error_message='',
                   raw_response=_sanitized_raw(data), **data)
