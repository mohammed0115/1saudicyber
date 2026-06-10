"""
Phase 3F — advisory AI/OCR evidence analysis pipeline.

Analyzes an EvidenceSubmission file and stores a DRAFT EvidenceAnalysisResult.
AI is an assistant ONLY: it never decides compliant/non-compliant, never accepts/
rejects evidence, never creates ControlAssessment. The final decision is the
auditor's (Phase 3G).

Safety:
  * text extraction is size/type limited; full file content is never logged.
  * heavy OCR (pdf/images) is intentionally NOT run here -> needs_human_review.
  * OpenAI key is read from settings/env only; missing key fails gracefully.
  * tenant scoping is the caller's responsibility (commands/views filter by company).

Standalone module (not a `services/` package) to avoid colliding with compliance/services.py.
"""
import json

from django.conf import settings
from django.utils import timezone

from compliance.models import EvidenceSubmission, EvidenceAnalysisResult

PROMPT_VERSION = 'advisory-v1'
MAX_EXTRACT_CHARS = 20000   # cap stored/extracted text
MAX_XLSX_ROWS = 500
TEXT_LIKE = {'txt', 'csv'}
# pdf/images deliberately deferred (no heavy OCR in this phase).
OCR_DEFERRED = {'pdf', 'png', 'jpg', 'jpeg'}

ADVISORY_SYSTEM_PROMPT = (
    "You are an assistant helping a human auditor review cybersecurity compliance evidence. "
    "You DO NOT make compliance decisions. You DO NOT mark anything compliant or non-compliant. "
    "You DO NOT accept or reject evidence. The final decision belongs to a human auditor. "
    "Given a control statement, an evidence requirement, and extracted evidence text, return a JSON "
    "object with keys: summary, requirement_match (how the evidence relates to the requirement), "
    "potential_gaps, risk_flags (array of short strings), confidence (0.0-1.0), needs_human_review "
    "(boolean). Never invent evidence that is not in the text. If the text is empty or insufficient, "
    "say so and set needs_human_review=true."
)


def extract_text_from_submission(submission):
    """Return (text, truncated, note). Size/type limited; no heavy OCR; no full-content logging."""
    ext = (submission.file_type or '').lower()
    try:
        if ext in TEXT_LIKE:
            with submission.uploaded_file.open('rb') as f:
                raw = f.read(MAX_EXTRACT_CHARS + 1)
            text = raw.decode('utf-8', errors='replace')
            truncated = len(raw) > MAX_EXTRACT_CHARS
            return text[:MAX_EXTRACT_CHARS], truncated, ''
        if ext == 'docx':
            try:
                from docx import Document
            except Exception:
                return '', False, 'python-docx not available'
            doc = Document(submission.uploaded_file.open('rb'))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            text = '\n'.join(parts)
            return text[:MAX_EXTRACT_CHARS], len(text) > MAX_EXTRACT_CHARS, ''
        if ext == 'xlsx':
            try:
                from openpyxl import load_workbook
            except Exception:
                return '', False, 'openpyxl not available'
            wb = load_workbook(submission.uploaded_file.open('rb'), read_only=True, data_only=True)
            parts, rows = [], 0
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        parts.append('\t'.join(cells)); rows += 1
                    if rows >= MAX_XLSX_ROWS:
                        break
                if rows >= MAX_XLSX_ROWS:
                    break
            wb.close()
            text = '\n'.join(parts)
            return text[:MAX_EXTRACT_CHARS], len(text) > MAX_EXTRACT_CHARS, ''
        if ext in OCR_DEFERRED:
            return '', False, 'OCR not available in advisory pipeline (deferred); needs human review'
        return '', False, f'unsupported file type: {ext}'
    except Exception as exc:  # never leak file content; only the error class/message
        return '', False, f'extraction error: {type(exc).__name__}'


def _run_ai(control, requirement, text):
    """Call the AI provider for an advisory analysis. Returns (result_dict, error, model, provider)."""
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    if not api_key:
        return None, 'AI provider not configured (no OPENAI_API_KEY)', '', ''
    try:
        from ai_engine.services import get_openai_client
        client = get_openai_client()
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        user = (f"CONTROL: {control.control_id} — {control.title}\n{control.description}\n\n"
                f"EVIDENCE REQUIREMENT: {getattr(requirement, 'title', '')} — "
                f"{getattr(requirement, 'description', '')}\n\n"
                f"EXTRACTED EVIDENCE TEXT:\n---\n{text[:8000]}\n---\n\n"
                "Return ONLY the JSON object described. The final compliance decision is the auditor's.")
        resp = client.chat.completions.create(
            model=model, temperature=0.2, response_format={'type': 'json_object'},
            messages=[{'role': 'system', 'content': ADVISORY_SYSTEM_PROMPT},
                      {'role': 'user', 'content': user}])
        data = json.loads(resp.choices[0].message.content)
        return data, '', model, 'openai'
    except Exception as exc:
        return None, f'AI error: {type(exc).__name__}', '', 'openai'


def analyze_evidence_submission(submission, *, apply=False):
    """Analyze one submission and (optionally) persist an EvidenceAnalysisResult. Idempotent.

    Never creates ControlAssessment/CompanyControl; never accepts/rejects evidence.
    """
    item = submission.checklist_item
    requirement = item.evidence_requirement
    control = requirement.control
    text, truncated, note = extract_text_from_submission(submission)

    # Decide status/content without making any compliance decision.
    fields = dict(
        company=submission.company, checklist_item=item, control=control,
        evidence_requirement=requirement, extracted_text=text,
        extracted_text_truncated=truncated, prompt_version=PROMPT_VERSION,
        risk_flags=[], analysis_metadata={'extraction_note': note})

    if not text:
        fields.update(status='needs_human_review',
                      error_message=note or 'No text extracted', summary='', confidence=None)
    else:
        data, err, model, provider = _run_ai(control, requirement, text)
        if data is None:
            fields.update(status='needs_human_review', error_message=err, model_used=model,
                          provider=provider, summary='', confidence=None)
        else:
            fields.update(
                status='completed', model_used=model, provider=provider,
                summary=str(data.get('summary', ''))[:4000],
                requirement_match=str(data.get('requirement_match', ''))[:4000],
                potential_gaps=str(data.get('potential_gaps', ''))[:4000],
                risk_flags=data.get('risk_flags', []) if isinstance(data.get('risk_flags'), list) else [],
                confidence=data.get('confidence') if isinstance(data.get('confidence'), (int, float)) else None,
                error_message='')

    if not apply:
        return {'submission': submission.id, 'would_status': fields['status'],
                'extracted_chars': len(text)}

    result, _ = EvidenceAnalysisResult.objects.update_or_create(
        evidence_submission=submission, defaults=fields)
    return {'submission': submission.id, 'status': result.status, 'id': result.id}


def batch_analyze_pending_submissions(company=None, *, apply=False):
    """Analyze submissions that have no completed analysis yet (optionally one company)."""
    qs = EvidenceSubmission.objects.all()
    if company is not None:
        qs = qs.filter(company=company)
    qs = qs.exclude(analysis__status='completed')
    results = [analyze_evidence_submission(s, apply=apply) for s in qs]
    return {'analyzed': len(results), 'results': results}
