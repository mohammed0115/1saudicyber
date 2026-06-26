# Phase 6C — Evidence Text Extraction Foundation

> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase extracts readable text only.
> This phase does **not** analyze evidence sufficiency.
> This phase does **not** determine compliance.
> This phase does **not** run AI.
> This phase does **not** implement OCR for scanned images (no safe existing OCR path is used here).

## What was implemented
A local, **safe, read-only** evidence text-extraction service that answers *"what readable text can we
safely extract from this evidence file?"* — preparation for later AI Evidence Analyzer / Rule Engine
phases. It is surfaced as a per-submission preview page and wired into the journey wizard. It never
judges evidence sufficiency or compliance.

## Supported file types
| Type | Method | Notes |
|---|---|---|
| **TXT / CSV / MD** | `plain_text` | UTF-8 read with `errors='replace'`, whitespace normalized |
| **PDF** | `pdf_text_layer` | `pdfplumber` text layer only — **no OCR**; image-only/scanned PDFs → `no_text_extracted` |
| **DOCX** | `docx` | `python-docx` paragraphs + table cells; no macros |
| **XLSX** | `xlsx` | `openpyxl` read-only, `data_only=True`, visible cell values, cell cap; no formula execution |

## Unsupported / OCR status
- **Images** (png/jpg/jpeg/tiff/bmp/gif/webp) → `no_text_extracted` with a warning that **OCR is planned
  for a later phase**. No OCR is performed in this phase (the existing `ai_engine` OCR path —
  pdf2image + pytesseract — is intentionally **not** used).
- Any other extension → `unsupported_type`.

## File size limits
- Extraction work is capped at **25 MB** (`MAX_EXTRACTION_BYTES`); larger files → `too_large`.
- Extracted text is capped at **50,000 chars** (`MAX_TEXT_CHARS`, sets `truncated`); PDF pages capped at
  300; XLSX cells capped at 20,000.

## Extraction service
- **Location:** [compliance/evidence_extraction.py](../compliance/evidence_extraction.py).
- **Input:** `extract_text_from_file(file_path, filename, content_type=None)` or
  `extract_text_from_evidence(evidence)` (EvidenceSubmission / legacy Evidence).
- **Output:** frozen `ExtractionResult` — `status`, `extracted_text`, `char_count`, `page_count`,
  `extraction_method`, `warnings`, `error_message`, `truncated` (+ `status_ar`, `has_text`).
- **Statuses:** `extracted`, `no_text_extracted`, `unsupported_type`, `too_large`, `failed`.
- **Parser safety:** extension is taken from the *declared filename only* (never a server path); missing
  file → `failed`; oversize → `too_large`; `ImportError` → `unsupported_type`; any parser exception →
  `failed` with a generic Arabic message (**no traceback, no path leaked**). No file content is ever
  executed; no macros/formulas run; no network/AI calls.
- **Determinism:** pure parsing → identical repeated results (tested).

## Storage decision
**On-demand, read-only — no model, no migration.** The preview is computed per request from the existing
`EvidenceSubmission.uploaded_file`. The legacy `Evidence.extracted_text` field is left untouched. No
persistence was needed for the foundation; later AI/Rule-Engine phases can persist if required.

## UI integration
- New read-only page **`/compliance/evidence-submissions/<id>/extraction/`**
  (`templates/compliance/evidence_extraction.html`): "استخراج النص من الدليل", a metadata strip
  (حالة الاستخراج / طريقة الاستخراج / عدد الأحرف / عدد الصفحات), "تنبيهات", the extracted text or
  "تعذر استخراج نص كافٍ من هذا الملف.", and the disclaimer
  **"هذا الاستخراج لا يمثل تحليلًا أو حكمًا على الامتثال."**
- A link to it was added on the evidence submission detail page.
- **i18n:** touched strings wrapped in `{% trans %}` and translated (e.g. "استخراج النص من الدليل" →
  "Evidence text extraction"). No compliance/final-verdict wording; the raw `/media/...` path is not shown.

## Journey integration
- **Evidence Upload** step → `completed` when any submission exists (unchanged).
- **Text Extraction** step (`ocr_extraction`, relabeled "استخراج النص من الأدلة", new kind `extraction`):
  `completed` when ≥1 uploaded submission is of a safely text-extractable type; `needs_action` when
  evidence exists but none is text-extractable (e.g. only images); `planned` before any upload (keeps it
  unavailable, preserving the existing "planned" semantics for a bare company). The type check is a fast
  heuristic — **no file is parsed during journey build**.
- OCR (scanned images), AI Analyzer, Rule Engine, Auditor Review, Final Verdict remain **not completed**.

## Security and tenant isolation
`@login_required`; anonymous → 302 to `/login`. The view loads the submission filtered by
`company=request.user.company`; another company's submission → not found → redirect (tested). The raw
file path is never rendered; parser errors never expose tracebacks or paths. No external calls, no DB
writes. Assigned-auditor access to this preview is intentionally **out of scope** this phase
(company-user-only); the existing auditor read-only pattern is unchanged.

## Tests run
- `EvidenceExtractionServiceTests` (11): TXT/CSV/DOCX/XLSX/PDF extraction, image → no_text, unsupported,
  too_large, missing file (no path leak), parser exception → failed (no traceback), text cap, whitespace
  normalization, determinism.
- `EvidenceExtractionUITests` (3): owner page renders + Arabic + disclaimer, no compliance/verdict/path,
  English mode.
- `EvidenceExtractionJourneyTests` (4): extraction planned without evidence, evidence-upload + extraction
  completed with an extractable file, needs_action with image-only evidence, downstream not completed.
- `EvidenceExtractionSecurityTests` (2): anonymous redirected, cross-company blocked.
- `manage.py check` clean; `makemigrations --check --dry-run` clean; full suite green.

## Known limitations
- No OCR for scanned images / image-only PDFs (planned later); those return `no_text_extracted`.
- Encrypted/password-protected PDFs and corrupt office files return `no_text_extracted`/`failed`.
- The journey completion signal is a file-*type* heuristic; a text-extractable file that happens to yield
  no text (e.g. an empty/scanned PDF) still marks the step completed by type — the per-file preview shows
  the true extraction result. Extraction is recomputed per request (not persisted).

## Out of scope (confirmed not implemented)
AI Evidence Analyzer, Rule Engine, compliance scoring/C-PC-NC, Compliance/Noncompliance, Auditor Final
Verdict, automated evidence sufficiency, CompanyControl generation, payment, external connectors,
monitoring alerting, database models, migrations, production deployment, secrets/`.env`.
