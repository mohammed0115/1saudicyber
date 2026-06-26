# Phase 6B — Applicability Engine Foundation

> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase does **not** determine compliance.
> This phase does **not** analyze evidence.
> This phase does **not** run AI.
> This phase does **not** run the Rule Engine or produce a final auditor verdict.
> This phase does **not** bulk-create CompanyControl rows.

## What was implemented
A local **deterministic, advisory** Applicability Engine that takes a company's profile/intake plus the
Phase 6A classification and previews **whether each official control appears to be in the company's
scope** — applicable / not applicable / needs-more-information — at both the framework level and the
control level. It answers *"is this control in scope?"*, never *"is the company compliant?"*. Surfaced on
a read-only page `/compliance/applicability/` and a journey-dashboard card.

## Input assumptions
Inputs come from existing data only (no new fields): `Company` (`sector`, `size`, `country`,
`cr_number`, `target_nca/aramco/sabic`) and `CompanyIntakeProfile` booleans (critical systems, cloud
usage/provider, remote work, official social media, Aramco/SABIC relationship, OT, sensitive/personal
data) — reused via Phase 6A's `classify_company`. When intake is missing, the engine does not guess: it
returns `needs_more_information` for not-indicated frameworks and lists the missing inputs.

## Applicability service
- **Location:** [compliance/applicability_engine.py](../compliance/applicability_engine.py).
- **Input:** the company + its Phase 6A classification (read-only).
- **Output dataclasses (named *Preview* to avoid clashing with the existing `ControlApplicabilityResult`
  model):** `ControlApplicabilityPreview` (control_id, framework_code, title, status, reason_ar/en,
  confidence, tags), `FrameworkApplicabilityPreview` (code, name, total_controls, applicable_count,
  not_applicable_count, needs_more_information_count, confidence, status), `ApplicabilityPreview`
  (company_id, generated_at, summaries, controls, missing_inputs, next_action, overall_confidence,
  has_intake).
- **Public functions:** `evaluate_company_applicability(company)` and
  `evaluate_control_applicability(company, control)`. **No DB writes** — read-only preview.
- **Framework-level rule:** map the Phase 6A classification status →
  required/recommended ⇒ `applicable`; optional ⇒ `needs_more_information` (likely in scope, needs
  confirmation); not_indicated ⇒ `not_applicable` when intake exists, else `needs_more_information`.
- **Control-level refinement:** conservative — only narrows an `applicable` framework result to
  `not_applicable` when a control explicitly scopes itself (`applies_to_sectors` / `applies_to_sizes`)
  to exclude the company. Never widens scope; never overfits free text.
- **Allowed statuses only:** `applicable`, `not_applicable`, `needs_more_information` (optional internal
  `likely_applicable`). **No** compliance statuses (C/PC/NC, Compliance/Noncompliance) — those belong to
  later Rule Engine / Auditor phases.

## Framework applicability logic
| Framework | Applicable when |
|---|---|
| **NCA ECC 2:2024** | KSA / `target_nca` / any intake cyber-signal (classification required/recommended) |
| **NCA CSCC** | `is_critical_system_operator` (critical-systems operator); else needs-info / not-applicable |
| **NCA CCC 2:2024** | `uses_cloud_services` or `provides_cloud_services` |
| **NCA TCC** | `has_remote_work` (telework) |
| **NCA OSMACC** | `manages_official_social_media_accounts` |
| **Aramco SACS-002** | `works_with_aramco` or `target_aramco` |
| **SABIC CyberTrust** | `works_with_sabic` or `target_sabic` |

## Control count source
Counts reuse the Phase 6A helper `official_control_count(version_code)` — live DB count of official
controls (`framework_version` set, `is_legacy_import=False`), falling back to the authoritative totals
when official controls aren't imported. Confirmed **official total = 417** (108+32+55+21+15+92+94);
the legacy **334** is never used (asserted by tests); counts are never hardcoded in templates.

## Control-level limitations
Where a DB has official controls imported, per-control previews are produced and refined by
`applies_to_sectors`/`applies_to_sizes`. Where official controls are not imported (e.g. a fresh/test DB),
the page shows the **framework-level** summary and notes that per-control detail appears after the
official control library is imported. No fragile per-control free-text heuristics were added.

## UI integration
- New read-only page **`/compliance/applicability/`** (`templates/compliance/applicability_preview.html`):
  title "قابلية تطبيق الضوابط", subtitle "تحليل استشاري لقابلية تطبيق الضوابط بناءً على بيانات الشركة.",
  the two required disclaimers ("هذا التحليل لا يقرر الامتثال أو عدم الامتثال." /
  "النتيجة النهائية تعتمد على الأدلة ومراجعة المدقق."), a framework summary table
  (الأطر / إجمالي الضوابط / قابلة للتطبيق / غير قابلة للتطبيق / تحتاج بيانات إضافية / مستوى الثقة),
  per-control list when available (with "سبب القرار"), "البيانات الناقصة", and "الخطوة التالية".
- **Journey-dashboard card** linking to it.
- **English/i18n:** touched strings wrapped in `{% trans %}` and translated (e.g. "قابلية تطبيق الضوابط"
  → "Control applicability", "إجمالي الضوابط" → "Total controls"). No compliance/final-verdict/certificate
  wording; no `334`.

## Journey integration
The journey **`applicability`** step is `completed` once an intake profile exists (an advisory
applicability preview is computable) **or** the persisted control plan has been generated; otherwise
`needs_action`. Downstream steps — Evidence Upload, OCR, AI Analyzer, Rule Engine, Auditor Review,
Final Verdict, Reports, Monitoring scheduling — are unchanged and remain not-completed (verified by tests).

## Security model
`@login_required`; anonymous → 302 to `/login`. The view evaluates only `request.user.company`; another
company's intake never bleeds in (tested). No cross-company access, no writes, no bulk generation.
Assigned-auditor access to this preview is intentionally **out of scope** this phase (company-user-only);
the existing read-only auditor pattern is unchanged.

## Tests run
- `ApplicabilityEngineServiceTests` (12): each framework rule, missing-intake → needs-info,
  not-indicated+intake → not-applicable, determinism, no-writes, allowed-statuses-only.
- `ApplicabilityCountTests` (2): total 417 (not 334), per-framework totals.
- `ApplicabilityUITests` (5): page renders + Arabic labels, disclaimers, no compliance/verdict/cert/334
  wording, dashboard card, English mode.
- `ApplicabilityJourneyTests` (3): step needs_action without intake, completed with intake, downstream
  steps stay not-completed.
- `ApplicabilitySecurityTests` (2): anonymous redirected, own-company only.
- `manage.py check` clean; `makemigrations --check --dry-run` clean (no model); full suite green.

## Data model / migration
**No model, no migration.** The preview is computed on demand (read-only). It deliberately does not write
to the existing `ControlApplicabilityResult` model (that persisted plan is produced by the separate
framework-scope pipeline, which this phase does not touch).

## Known limitations
- Framework-level applicability is the primary signal; control-level refinement only triggers on explicit
  `applies_to_sectors`/`applies_to_sizes` scope fields.
- Without an intake profile, not-indicated frameworks surface as `needs_more_information` (conservative),
  and overall confidence is reduced.
- The preview is recomputed per request (not persisted).

## Out of scope (confirmed not implemented)
OCR, AI Evidence Analyzer, Rule Engine compliance status, Auditor Final Verdict, evidence scoring,
CompanyControl/applicability bulk generation, report calculation rewrite, payment, external connectors,
monitoring alerting, database models, migrations, production deployment, secrets/`.env`.
