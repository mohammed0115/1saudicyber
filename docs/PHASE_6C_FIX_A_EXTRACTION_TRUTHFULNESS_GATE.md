# Phase 6C-FIX-A — Extraction Result Truthfulness Gate

> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase only makes extraction status truthful.
> This phase does **not** analyze evidence sufficiency.
> This phase does **not** determine compliance.
> This phase does **not** run AI.
> This phase does **not** implement OCR.

## Why the fix was needed
Phase 6C marked the journey **Text Extraction** step `completed` from a file-*type* heuristic — a
PDF/DOCX/XLSX counted as "extracted" even if it had no readable text or failed parsing. That is
misleading ahead of Phase 6D (AI Evidence Analyzer). This phase makes the step reflect an **actual,
persisted successful extraction**.

## Persistence decision
**Option B — additive lightweight model.** No existing field safely stored a pure extraction attempt
(`EvidenceAnalysisResult` is the AI-analysis model and conflates extraction with advisory analysis). Added:
- `EvidenceTextExtraction` (OneToOne → `EvidenceSubmission`): `status`, `extracted_text`, `char_count`,
  `page_count`, `extraction_method`, `warnings` (JSON), `error_message`, `truncated`, `extracted_at`.
- Migration **`compliance/0012_evidencetextextraction.py`** — additive (creates one new table only; no
  changes to existing tables/columns). Statuses: `extracted`, `no_text_extracted`, `unsupported_type`,
  `too_large`, `failed`.
- Registered in admin **read-only** (all fields read-only, add disabled) — extraction is computed by the
  service, never hand-edited.

## Extraction action / flow
New helper `save_extraction_for_submission(submission)` runs the existing safe extractor and **upserts**
(`update_or_create`) the single `EvidenceTextExtraction` row (re-run updates, never duplicates).

New POST action **`POST /compliance/evidence-submissions/<id>/extract-text/`**
(`run_evidence_extraction`): POST-only (`require_http_methods(["POST"])`), CSRF-protected,
owner-company only, no external calls, redirects back to the preview with an Arabic message —
`تم استخراج النص من الدليل.` (extracted) / `تعذر استخراج نص كافٍ من هذا الملف.` (no text) /
`تعذر تنفيذ الاستخراج بأمان.` (failed). Extraction is **not** run automatically on upload.

## Journey status rules
- **Evidence Upload** → `completed` when any submission exists.
- **Text Extraction** (`ocr_extraction`) → `completed` **only** when a persisted `EvidenceTextExtraction`
  with `status='extracted'` and `char_count>0` exists; `needs_action` when evidence exists but no such
  successful result (not attempted, no-text, image-only, or failed); `planned` when no evidence exists.
  The builder reads the **persisted status** only — it never parses files.
- **OCR (scanned images)** → still `planned`/not available.
- **AI Analyzer / Rule Engine / Auditor Review / Final Verdict** → remain not completed.

## UI truthfulness
The preview page now shows the **persisted** result:
- **Not attempted:** "لم يتم تشغيل استخراج النص بعد." + a "تشغيل استخراج النص" button; no result metadata
  (does not imply success).
- **Extracted:** metadata strip (status/method/chars/pages), warnings, and "النص المستخرج".
- **No text:** "تعذر استخراج نص كافٍ من هذا الملف.".
- A "إعادة استخراج النص" button re-runs when a result already exists.
- The disclaimer **"هذا الاستخراج لا يمثل تحليلًا أو حكمًا على الامتثال."** remains; no compliance/verdict
  wording; raw `/media/...` path never rendered. Touched strings use `{% trans %}` (English catalog updated).

## Security / tenant isolation
`@login_required`; anonymous → 302 to `/login`. Both the preview and the POST action load the submission
filtered by `company=request.user.company`; another company's submission → redirect, and the POST writes
nothing (tested). POST-only action (GET → 405). Parser errors never expose tracebacks or file paths.
No external/AI calls. Assigned-auditor access remains out of scope (company-user-only).

## Tests run
- `EvidenceExtractionServiceTests` (11, regression) — unchanged, still pass (no AI/network).
- `EvidenceExtractionUITests` (4): not-attempted state (no false success) + run button, extracted state
  shows stored result, no compliance/verdict/path, English mode.
- `EvidenceExtractionPersistenceTests` (6): run action persists one result, re-run updates not
  duplicates, warnings stored + no path, GET→405, anonymous redirect, cross-company blocked (no write).
- `EvidenceExtractionJourneyTests` (5): planned without evidence, extractable-but-not-run → needs_action,
  completed only after successful extraction, no-text keeps needs_action, downstream not completed.
- `EvidenceExtractionSecurityTests` (2): anonymous redirect, cross-company preview blocked.
- `manage.py check` clean; `makemigrations --check --dry-run` clean after migrate; full suite green.

## Known limitations
- No OCR for scanned images / image-only PDFs (planned later) → those persist `no_text_extracted` and the
  step stays `needs_action`, which is the truthful state.
- Extraction is user-triggered (no auto-extract on upload, no background worker introduced).
- Encrypted/corrupt files persist `no_text_extracted`/`failed`.

## Out of scope (confirmed not implemented)
AI Evidence Analyzer, OCR, Rule Engine, compliance/evidence-sufficiency judgment, Auditor Final Verdict,
CompanyControl generation, payment, external connectors, monitoring alerting, destructive migration,
production deployment, secrets/`.env`.
