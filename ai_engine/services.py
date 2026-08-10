"""
AI Engine Services - OpenAI Integration + OCR
The brain of CyberTrust KSA platform.
"""
import json
import time
import os
from django.conf import settings
from openai import OpenAI
import pytesseract
from PIL import Image
from pdf2image import convert_from_path


def ai_enabled():
    """True only when an OpenAI API key is configured. External AI is advisory-only."""
    return bool((getattr(settings, 'OPENAI_API_KEY', '') or '').strip())


def ai_data_residency_mode():
    """Current data-sovereignty mode: 'disabled' | 'external' | 'local'."""
    return (getattr(settings, 'AI_DATA_RESIDENCY_MODE', 'disabled') or 'disabled').strip().lower()


def external_ai_allowed():
    """External LLM calls send text out of the Kingdom — require BOTH an explicit
    'external' data-residency opt-in AND a configured API key. Default is fail-closed:
    no evidence/company text leaves unless deliberately enabled (PDPL / NCA classification)."""
    return ai_data_residency_mode() == 'external' and ai_enabled()


def ai_advisory_state():
    """(available, reason_ar) for the advisory AI service — an honest, user-facing state.

    Distinguishes the two fail-closed reasons so the UI never shows a vague 'unavailable'.
    """
    if not ai_enabled():
        return False, 'التحليل الآلي غير مُفعّل على هذه البيئة (لا يوجد مفتاح).'
    if ai_data_residency_mode() != 'external':
        return False, ('التحليل الآلي معطّل بسياسة سيادة البيانات — '
                       'لتفعيله اضبط AI_DATA_RESIDENCY_MODE=external.')
    return True, 'التحليل الاستشاري مُفعّل (استشاري فقط، ليس قرارًا نهائيًا).'


class ExternalAINotAllowed(RuntimeError):
    """The data-residency policy forbids constructing/using the external-AI client.

    Central provider-boundary tripwire (P0-04): raised by get_openai_client() so a caller that
    forgets its own residency guard cannot silently egress tenant data — it fails LOUD and safe.
    """


def get_openai_client(*, allow_public_reference=False):
    """Construct the external OpenAI client — FAIL-CLOSED at the provider boundary (P0-04).

    This is the single choke point for external-AI egress. By default it refuses to build the
    client unless external_ai_allowed() (residency == 'external' AND a configured key), so no
    tenant evidence/company text can leave the Kingdom just because a key exists or a caller
    forgot its guard — the caller gets a loud ExternalAINotAllowed instead of a silent send.

    allow_public_reference=True is the ONE documented exception: the translate_controls_ar
    command sends PUBLIC regulatory control text (NCA/Aramco/SABIC standards — not tenant/company
    data), so it is exempt from the tenant residency gate but STILL requires a configured key.
    Nothing that handles tenant/company content may set this.
    """
    if allow_public_reference:
        if not ai_enabled():
            raise ExternalAINotAllowed('No API key configured for external AI.')
    elif not external_ai_allowed():
        raise ExternalAINotAllowed(
            'External AI is disabled by the data-residency policy '
            '(AI_DATA_RESIDENCY_MODE is not "external", or no API key).')
    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=2)


# ============================================================
# OCR SERVICE
# ============================================================

def extract_text_from_image(image_path):
    """Extract text from an image file using Tesseract OCR."""
    try:
        image = Image.open(image_path)
        # Try Arabic + English
        text_ar = pytesseract.image_to_string(image, lang='ara+eng')
        confidence_data = pytesseract.image_to_data(image, lang='ara+eng', output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in confidence_data['conf'] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            'text': text_ar.strip(),
            'confidence': avg_confidence / 100.0,
            'language': 'ar+en',
        }
    except Exception as e:
        return {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using OCR (converts pages to images first)."""
    try:
        images = convert_from_path(pdf_path, dpi=300)
        all_text = []
        total_confidence = 0.0

        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image, lang='ara+eng')
            all_text.append(f"--- Page {i+1} ---\n{text}")
            confidence_data = pytesseract.image_to_data(image, lang='ara+eng', output_type=pytesseract.Output.DICT)
            confidences = [int(c) for c in confidence_data['conf'] if int(c) > 0]
            if confidences:
                total_confidence += sum(confidences) / len(confidences)

        avg_confidence = (total_confidence / len(images)) / 100.0 if images else 0.0
        return {
            'text': '\n\n'.join(all_text),
            'confidence': avg_confidence,
            'language': 'ar+en',
            'pages': len(images),
        }
    except Exception as e:
        return {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}


def extract_text_from_docx(path):
    """Extract text from a Word .docx file (paragraphs + tables)."""
    try:
        from docx import Document
        doc = Document(path)
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(' | '.join(cells))
        return {'text': '\n'.join(parts).strip(), 'confidence': 1.0, 'language': 'unknown'}
    except Exception as e:
        return {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}


def extract_text_from_xlsx(path):
    """Extract text from an Excel .xlsx workbook (all sheets, all cells)."""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            parts.append(f"## Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    parts.append('\t'.join(cells))
        wb.close()
        return {'text': '\n'.join(parts).strip(), 'confidence': 1.0, 'language': 'unknown'}
    except Exception as e:
        return {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}


def process_uploaded_file(file_path, file_type):
    """Process any uploaded file and extract text (OCR for scans/images, parsers for office docs)."""
    file_type_lower = file_type.lower()
    if file_type_lower == 'pdf':
        return extract_text_from_pdf(file_path)
    elif file_type_lower in ['png', 'jpg', 'jpeg', 'tiff', 'bmp']:
        return extract_text_from_image(file_path)
    elif file_type_lower == 'docx':
        return extract_text_from_docx(file_path)
    elif file_type_lower in ['xlsx', 'xlsm']:
        return extract_text_from_xlsx(file_path)
    elif file_type_lower in ['txt', 'csv', 'md']:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return {'text': f.read(), 'confidence': 1.0, 'language': 'unknown'}
        except Exception as e:
            return {'text': '', 'confidence': 0.0, 'language': '', 'error': str(e)}
    else:
        return {'text': '', 'confidence': 0.0, 'language': '', 'error': f'Unsupported file type: {file_type}'}


# ============================================================
# AI CLASSIFICATION ENGINE
# ============================================================

CLASSIFICATION_SYSTEM_PROMPT = """You are CyberTrust KSA's AI Classification Engine. You are an expert in Saudi Arabian cybersecurity compliance frameworks including:
- NCA ECC (National Cybersecurity Authority - Essential Cybersecurity Controls)
- Aramco SACS-002 (Third Party Cybersecurity Standard)
- SABIC CyberTrust Standard

Your role is to analyze a company's profile (sector, size, vendor targets) and determine:
1. The exact control sets required for this company
2. The risk level (low/medium/high/critical)
3. Priority domains to focus on
4. Estimated timeline for compliance
5. Key challenges specific to this company type

Respond in JSON format with both English and Arabic content."""

def classify_company(company_data):
    """
    AI-powered company classification.
    Determines applicable controls and risk level based on company profile.
    """
    # Fail-closed: no key OR external AI not opted-in (data residency) -> safe advisory
    # result; company text never leaves the Kingdom unless AI_DATA_RESIDENCY_MODE=external.
    if not external_ai_allowed():
        return {'ai_available': False, 'residency_mode': ai_data_residency_mode(),
                'risk_level': 'medium',
                'summary_en': 'AI classification not available (external AI disabled by data-residency policy).',
                'summary_ar': 'التصنيف الآلي غير متاح (الذكاء الخارجي معطّل بسياسة سيادة البيانات).'}
    start_time = time.time()

    user_prompt = f"""Analyze this company and classify its cybersecurity compliance requirements:

Company Name: {company_data['name']}
Sector: {company_data['sector']}
Size: {company_data['size']}
Target Frameworks:
- Aramco SACS-002: {'Yes' if company_data.get('target_aramco') else 'No'}
- SABIC CyberTrust: {'Yes' if company_data.get('target_sabic') else 'No'}
- NCA ECC (Government): {'Yes' if company_data.get('target_nca') else 'No'}

Provide your analysis in this JSON structure:
{{
    "risk_level": "low|medium|high|critical",
    "summary_en": "Brief classification summary in English",
    "summary_ar": "Brief classification summary in Arabic",
    "applicable_domains": ["list of priority compliance domains"],
    "estimated_controls_count": number,
    "estimated_timeline_months": number,
    "key_challenges_en": ["list of challenges in English"],
    "key_challenges_ar": ["list of challenges in Arabic"],
    "priority_actions_en": ["immediate actions needed in English"],
    "priority_actions_ar": ["immediate actions needed in Arabic"],
    "compliance_readiness_score": 0-100
}}"""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        processing_time = int((time.time() - start_time) * 1000)
        result = json.loads(response.choices[0].message.content)
        result['model_used'] = settings.OPENAI_MODEL
        result['prompt_tokens'] = response.usage.prompt_tokens
        result['completion_tokens'] = response.usage.completion_tokens
        result['processing_time_ms'] = processing_time
        return result

    except Exception as e:
        return {'error': str(e), 'ai_available': False, 'risk_level': 'medium',
                'summary_en': 'Classification pending', 'summary_ar': 'التصنيف قيد المعالجة'}


# ============================================================
# AI EVIDENCE AUDITOR
# ============================================================

AUDITOR_SYSTEM_PROMPT = """You are CyberTrust KSA's AI Auditor. You are an expert cybersecurity compliance auditor specializing in Saudi Arabian frameworks (NCA ECC, Aramco SACS-002, SABIC CyberTrust).

Your role is to analyze uploaded evidence documents against specific compliance controls and determine:
1. Whether the evidence demonstrates compliance with the control
2. Your confidence level in the assessment
3. Detailed reasoning for your verdict
4. Specific recommendations for improvement

You must provide verdicts in both Arabic and English.
Be thorough, precise, and reference specific sections of the evidence that support your verdict."""

def analyze_evidence(extracted_text, control_data):
    """
    AI-powered evidence analysis.
    Analyzes extracted text against a specific compliance control.
    """
    # Fail-closed on data residency: evidence text must NOT be sent to an external LLM
    # unless AI_DATA_RESIDENCY_MODE=external (and a key is set). Otherwise return a safe
    # "insufficient — pending human review" result. Never a final verdict.
    if not external_ai_allowed():
        return {'ai_available': False, 'residency_mode': ai_data_residency_mode(),
                'verdict': 'insufficient_evidence', 'confidence': 0.0,
                'reasoning_en': 'AI analysis not available (external AI disabled by data-residency policy) — pending human review.',
                'reasoning_ar': 'التحليل الآلي غير متاح (الذكاء الخارجي معطّل بسياسة سيادة البيانات) — بانتظار مراجعة بشرية.'}
    start_time = time.time()

    user_prompt = f"""Analyze this evidence document against the following compliance control:

CONTROL INFORMATION:
- Control ID: {control_data['control_id']}
- Framework: {control_data['framework']}
- Title: {control_data['title']}
- Description: {control_data['description']}
- Required Evidence Type: {control_data.get('evidence_type', 'Any')}

EXTRACTED DOCUMENT TEXT:
---
{extracted_text[:8000]}
---

Provide your analysis in this JSON structure:
{{
    "verdict": "compliant|non_compliant|partially_compliant|insufficient_evidence",
    "confidence": 0.0-1.0,
    "reasoning_en": "Detailed reasoning in English explaining why this verdict was reached",
    "reasoning_ar": "التفسير المفصل بالعربية",
    "key_findings_en": ["specific findings from the document"],
    "key_findings_ar": ["النتائج المحددة من الوثيقة"],
    "recommendations_en": ["specific recommendations for improvement"],
    "recommendations_ar": ["التوصيات المحددة للتحسين"],
    "evidence_quality": "high|medium|low",
    "missing_elements": ["elements that should be present but are missing"],
    "risk_if_unresolved": "description of risk if this gap remains"
}}"""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        processing_time = int((time.time() - start_time) * 1000)
        result = json.loads(response.choices[0].message.content)
        result['model_used'] = settings.OPENAI_MODEL
        result['prompt_tokens'] = response.usage.prompt_tokens
        result['completion_tokens'] = response.usage.completion_tokens
        result['processing_time_ms'] = processing_time
        return result

    except Exception as e:
        return {'error': str(e), 'ai_available': False,
                'verdict': 'insufficient_evidence', 'confidence': 0.0}


# ============================================================
# GAP ANALYSIS & PREDICTIVE RISK
# ============================================================

GAP_ANALYSIS_PROMPT = """You are CyberTrust KSA's AI Risk Analyst. Analyze the compliance status of a company and provide:
1. Gap analysis identifying missing or weak controls
2. Risk scoring for each gap
3. Probability of an auditor finding each gap
4. Prioritized remediation roadmap
5. Predicted timeline to achieve compliance

Provide analysis in both Arabic and English."""

def generate_gap_analysis(company_data, controls_status):
    """
    AI-powered gap analysis and predictive risk assessment.
    """
    # Fail-closed on data residency: company data must not leave the Kingdom for an
    # external LLM unless AI_DATA_RESIDENCY_MODE=external (and a key is set).
    if not external_ai_allowed():
        return {'ai_available': False, 'residency_mode': ai_data_residency_mode(),
                'overall_risk_score': 0, 'compliance_score': 0,
                'predicted_audit_outcome_en': 'AI gap analysis not available (external AI disabled by data-residency policy).',
                'predicted_audit_outcome_ar': 'تحليل الفجوات الآلي غير متاح (الذكاء الخارجي معطّل بسياسة سيادة البيانات).'}
    start_time = time.time()

    user_prompt = f"""Perform a comprehensive gap analysis for this company:

COMPANY: {company_data['name']}
SECTOR: {company_data['sector']}
SIZE: {company_data['size']}
TARGET FRAMEWORKS: {', '.join(company_data.get('frameworks', []))}

CURRENT COMPLIANCE STATUS:
{json.dumps(controls_status, indent=2)[:6000]}

Provide your analysis in this JSON structure:
{{
    "overall_risk_score": 0-100,
    "compliance_score": 0-100,
    "critical_gaps": [
        {{
            "control_id": "...",
            "domain": "...",
            "gap_description_en": "...",
            "gap_description_ar": "...",
            "risk_level": "critical|high|medium|low",
            "auditor_finding_probability": 0.0-1.0,
            "remediation_effort": "days|weeks|months",
            "remediation_steps_en": ["..."],
            "remediation_steps_ar": ["..."]
        }}
    ],
    "domain_scores": {{"domain_name": score}},
    "predicted_audit_outcome_en": "...",
    "predicted_audit_outcome_ar": "...",
    "time_to_compliance_months": number,
    "top_priorities_en": ["..."],
    "top_priorities_ar": ["..."]
}}"""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": GAP_ANALYSIS_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        processing_time = int((time.time() - start_time) * 1000)
        result = json.loads(response.choices[0].message.content)
        result['processing_time_ms'] = processing_time
        return result

    except Exception as e:
        return {'error': str(e), 'ai_available': False,
                'overall_risk_score': 0, 'compliance_score': 0}
