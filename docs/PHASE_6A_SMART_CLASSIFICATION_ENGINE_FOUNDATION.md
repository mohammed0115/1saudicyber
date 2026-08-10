# Phase 6A — Smart Classification Engine Foundation

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase does **not** generate final compliance decisions.
> This phase does **not** run AI evidence analysis.
> This phase does **not** generate CompanyControl / applicability rows.

## What was implemented
A local **deterministic, advisory** Smart Classification layer that reads a company's existing
profile + intake data and produces an advisory **"تصنيف أولي استشاري"**:
- recommended compliance frameworks (with status + reason + expected control count + confidence)
- a deterministic risk level
- the missing inputs that would sharpen the result
- a clear next action

It is presented on a dedicated read-only page (`/compliance/classification/`) and as a summary card on
the journey dashboard. It is **advisory only** — it never certifies, never decides compliance, and never
writes data.

## Input assumptions
Inputs come from existing data only (no new risky UI fields were added):
- `Company`: `sector`, `size`, `country`, `cr_number`, `target_nca` / `target_aramco` / `target_sabic`.
- `CompanyIntakeProfile` (if present): `is_government_entity`, `is_critical_system_operator`,
  `uses_cloud_services`, `provides_cloud_services`, `handles_sensitive_data`, `handles_personal_data`,
  `has_ot_environment`, `has_remote_work`, `manages_official_social_media_accounts`,
  `works_with_aramco`, `works_with_sabic`.

When the intake profile is absent, the engine uses the company fields, **marks the missing inputs
explicitly**, lowers overall confidence (capped at 60), and recommends completing the intake.

## Rules used (deterministic — no AI, no randomness, no network)
Service: [compliance/smart_classification.py](../compliance/smart_classification.py). It mirrors the
signal semantics already used by the deterministic applicability engine
(`compliance/framework_applicability.py`) so the advisory summary stays consistent, **without
re-running or rewriting it**.

| Framework (version code) | Recommended when | Status | Count |
|---|---|---|---|
| NCA ECC 2:2024 (`NCA-ECC-2-2024`) | any intake cyber signal, or `target_nca`, or operating in KSA (baseline) | required (or recommended) | 108 |
| NCA CSCC (`NCA-CSCC-1-2019`) | `is_critical_system_operator`; else critical sector → optional | recommended / optional / not_indicated | 32 |
| NCA CCC 2:2024 (`NCA-CCC-2-2024`) | `uses_cloud_services` or `provides_cloud_services`; else technology sector → optional | recommended / optional / not_indicated | 55 |
| NCA TCC (`NCA-TCC-1-2021`) | `has_remote_work` | recommended / not_indicated | 21 |
| NCA OSMACC (`NCA-OSMACC-1-2021`) | `manages_official_social_media_accounts` | recommended / not_indicated | 15 |
| Aramco SACS-002 (`ARAMCO-SACS-002`) | `works_with_aramco` or `target_aramco`; else oil&gas sector → optional | required / optional / not_indicated | 92 |
| SABIC CyberTrust (`SABIC-CYBERTRUST-1-0`) | `works_with_sabic` or `target_sabic`; else petrochemical/manufacturing → optional | required / optional / not_indicated | 94 |

When a framework is not indicated, the engine says **"غير مُشار إليه حاليًا بناءً على البيانات المتاحة"**
— never "impossible". Confidence is a deterministic 0–100 score per recommendation (explicit intake
signal = highest, legacy target checkbox = medium, sector-inferred = lower, KSA baseline = medium-high).

**Risk level** is deterministic from sector + size + signals: critical sectors / critical-systems / OT
→ `high`; medium sectors / large-enterprise / sensitive-personal data / Aramco-SABIC ties → `medium`;
otherwise `low`; `unknown` only when sector is blank.

> Note on the brief's CSCC trigger: CSCC is the **Critical Systems** Cybersecurity Controls (count 32).
> It is mapped here to its real critical-systems semantics (`is_critical_system_operator` / critical
> sector); cloud usage drives **CCC** (count 55). Counts match the brief exactly.

## Control count source
Counts are produced by `official_control_count(version_code)`, which prefers the **live DB count** of
official controls (`Control.objects.filter(framework_version__code=…, is_legacy_import=False).count()`)
and falls back to the authoritative official total when official controls are not yet imported
(e.g. a fresh/test DB). The canonical totals are **108/32/55/21/15/92/94 = 417**. The legacy **334**
set is never used (asserted by tests), and counts are never hardcoded in templates.

## UI integration
- New read-only page **`/compliance/classification/`** (`templates/compliance/classification.html`):
  title "التصنيف الذكي", advisory subtitle "تصنيف أولي استشاري بناءً على بيانات الشركة." with an
  explicit "لا يُعد قرارًا نهائيًا أو شهادة" note; risk level, recommended-framework count, expected
  control count, confidence; a per-framework list (status badge, reason "سبب التصنيف", "عدد الضوابط
  المتوقع"); "البيانات الناقصة"; and "الخطوة التالية".
- Summary **card on the journey dashboard** linking to the page.
- English mode: all touched strings are wrapped in `{% trans %}` and translated in the catalogs
  (e.g. "التصنيف الذكي" → "Smart Classification", "مستوى المخاطر" → "Risk level").
- No `334`, no certificate/certified, no final-decision wording.

## Journey Wizard integration
The **Smart Classification** step (`smart_classification`) is now `completed` once an intake profile
exists (the classification is computable) **or** deterministic applicability has been run; otherwise it
remains `needs_action`. The planned steps (OCR, Rule Engine, AI Analyzer, Final Verdict) are unchanged
and remain not-completed.

## Tests run
- `SmartClassificationServiceTests` (11): ECC/CSCC/CCC/TCC/OSMACC/Aramco/SABIC rules, not-indicated
  wording, incomplete-profile missing inputs + lower confidence, determinism.
- `SmartClassificationCountTests` (3): total 417 (not 334), per-framework counts, DB-preferred helper.
- `SmartClassificationUITests` (4): page renders, no certification/final-decision wording, dashboard
  card, English mode.
- `SmartClassificationJourneyTests` (3): step needs_action without intake, completed with intake,
  planned steps stay not-completed.
- `SmartClassificationSecurityTests` (2): anonymous redirected; only own-company data classified.
- `manage.py check` clean; `makemigrations --check --dry-run` clean (no model added); full suite green.

## Data model / migration
**No model, no migration.** The result is computed on demand from existing `Company` +
`CompanyIntakeProfile` data (read-only), so no persistence was needed. `Company` already carries
`risk_level` / `classification_*` fields for the legacy AI summary; this phase does not touch them.

## Known limitations
- CSCC/CCC/Aramco/SABIC sector-only inferences are intentionally `optional` (lower confidence) and ask
  for confirmation, because the precise signals live in the intake profile.
- Without an intake profile, only company-level fields drive the result; the engine flags this and
  caps confidence at 60.
- The advisory result is not persisted; it is recomputed per request (cheap, deterministic).

## Out of scope (confirmed not implemented)
OCR, AI Evidence Analyzer, Rule Engine, Applicability Engine (re-run/rewrite), CompanyControl
generation, final compliance/auditor decision, payment, external connectors, alerts, report/subscription/
auditor/risk/control decision rewrite, upload workflow, frontend stack replacement, database models,
migrations, production deployment, secrets/`.env`.
