# Phase 6D — AI Evidence Analyzer Advisory

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase is advisory only.
> This phase does **not** determine compliance.
> This phase does **not** run the Rule Engine.
> This phase does **not** create an Auditor Final Verdict.
> This phase **requires extracted text** before analysis.

## What was implemented
A local, **advisory, mockable** AI Evidence Analyzer that reads the PERSISTED extracted text of an
`EvidenceSubmission` (from Phase 6C-FIX-A) and stores an advisory `EvidenceAIAnalysis`: relevance,
confidence, summary, matched signals, missing items, recommendations. It helps a human auditor and
never decides compliance. Surfaced as a per-submission preview page with a POST run action and wired
into the journey wizard.

## Extraction gate
`can_analyze_submission(submission)` returns `(ok, reason_ar)`; analysis runs only when a persisted
`EvidenceTextExtraction` exists with `status='extracted'`, `char_count>0`, and non-blank text. Otherwise
the provider is **never called** and the UI/POST shows
**"يجب استخراج نص قابل للقراءة من الدليل قبل تشغيل التحليل الاستشاري."** The service itself also
enforces the gate (returns a `skipped` result without calling the provider).

## AI provider strategy
Provider is an injectable abstraction (`EvidenceAnalyzerProvider.analyze(prompt) -> dict`):
- Default `OpenAIEvidenceProvider` reuses the existing `ai_engine.get_openai_client` and
  `settings.OPENAI_API_KEY`/`OPENAI_MODEL`. If **no key is configured** it raises `ProviderUnavailable`,
  which the service converts to a safe **`skipped`** state (never a crash). No key is printed or committed.
- `default_provider()` is a patchable factory; **tests inject a fake provider** — there are **no real
  network calls in tests**. Views never call OpenAI directly.

## Prompt / response validation
`build_prompt(submission, extraction)` includes the control id/title/description, framework code, a
**capped** extracted-text excerpt (8,000 chars), a strict **advisory-only** instruction ("ADVISORY ONLY …
DO NOT decide compliance …"), and the required JSON shape. It **never includes a file path or secret**.
`_validate` clamps `confidence` to 0–100, restricts `relevance` to `high|medium|low|unclear` (anything
else → `unclear`), caps the summary and each list (count + length), and marks the result **`failed`** if
the response is not a dict. Only the sanitized, capped keys are stored in `raw_response`.

## Advisory analysis service
- **Location:** [compliance/evidence_ai_analyzer.py](../compliance/evidence_ai_analyzer.py).
- `analyze_submission_evidence(submission, provider=None, actor=None)` → upserts one `EvidenceAIAnalysis`
  per submission (re-run updates, never duplicates).
- **Statuses:** `completed`, `skipped` (gate not met / provider unavailable), `failed` (invalid response
  or provider exception — generic Arabic message, **no raw exception leaked**).
- Never writes `ControlAssessment`/`CompanyControl`/reports; never produces a compliance status.

## Data model / migration
**Additive model** `EvidenceAIAnalysis` (OneToOne → `EvidenceSubmission`): status, relevance, confidence,
summary, matched_signals, missing_items, recommendations (JSON), raw_response (JSON), error_message,
analyzed_at. Migration **`compliance/0013_evidenceaianalysis.py`** — additive (1 CreateModel, 0
destructive ops). Registered in admin **read-only** (add disabled). The legacy Phase 3F
`EvidenceAnalysisResult` is left untouched (distinct model/flow).

## UI integration
- New page **`/compliance/evidence-submissions/<id>/ai-analysis/`**
  (`templates/compliance/evidence_ai_analysis.html`): "التحليل الاستشاري للذكاء الاصطناعي", the
  disclaimer "هذا التحليل يساعد المدقق ولا يُعد قرارًا نهائيًا أو شهادة امتثال. النتيجة النهائية تعتمد على
  الأدلة ومراجعة المدقق.", a gate message + extraction link when text is missing, a run/re-run button,
  and (when completed) status / relevance / confidence + summary / matched signals / missing items /
  advisory recommendations.
- POST **`/compliance/evidence-submissions/<id>/run-ai-analysis/`**.
- Linked from the submission detail page. Touched strings use `{% trans %}` (English catalog updated).
- No C/PC/NC, no Compliance/Noncompliance, no final-verdict/certificate wording; raw file path never shown.

## Journey integration
The `ai_analysis` step (kind `ai_analysis`): **completed** only when a persisted `EvidenceAIAnalysis`
with `status='completed'` exists; **needs_action** when extracted text exists but no completed analysis;
**planned** when no extracted text exists. Rule Engine, Auditor Review, and Final Verdict remain not
completed.

## Security / tenant isolation
`@login_required`; anonymous → 302 `/login`. Preview and POST load the submission filtered by
`company=request.user.company`; cross-company → redirect and the POST writes nothing (tested). Run action
is POST-only (GET → 405). Provider errors are caught and never surface tracebacks; no secrets in UI/logs;
no file path leaked. Assigned-auditor access is out of scope this phase (company-user-only).

## Tests run
- `AIAnalyzerGateTests` (3): no extraction / no_text / failed → cannot analyze; extracted+text → can.
- `AIAnalyzerServiceTests` (10): completed via fake provider, rerun updates (no duplicates), gate blocks
  provider call, invalid response → failed, provider exception → failed (no leak), provider-unavailable →
  skipped, confidence clamped, relevance restricted, prompt advisory + no path/secret, no final-compliance
  wording stored.
- `AIAnalyzerUITests` (5): preview renders, gate warning, POST run with fake provider, no C/PC/NC or
  verdict wording, English mode.
- `AIAnalyzerJourneyTests` (4): planned without extraction, needs_action with extraction but no analysis,
  completed after completed analysis, downstream not completed.
- `AIAnalyzerSecurityTests` (4): anonymous redirect, cross-company view blocked, cross-company POST writes
  nothing, GET run → 405.
- `manage.py check` clean; `makemigrations --check --dry-run` clean after migrate; full suite green.

## Known limitations
No final compliance decision, no Rule Engine, no auditor verdict (later phases). Requires extracted text
first. With no AI key configured locally, runs resolve to a safe `skipped` state (the real provider call
is exercised only with a configured key, never in tests). Advisory output quality depends on the provider.

## Out of scope (confirmed not implemented)
Rule Engine, compliance judgment, Auditor Final Verdict, CompanyControl generation, OCR, payment,
external integration beyond the configured AI provider abstraction, monitoring alerting, report/
subscription/auditor/risk/control decision rewrite, upload rewrite, frontend replacement, production
deployment, destructive migration, secrets/`.env`.
