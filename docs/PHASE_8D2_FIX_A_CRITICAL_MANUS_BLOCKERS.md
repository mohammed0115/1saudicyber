# Phase 8D-2-FIX-A — Critical Manus Blockers

> **Branding note:** Public brand **1SaudiCyber — 1saudicyber.com**; internal package `cybertrust_ksa`.
> Local code only — no deployment, no SSH, no migration, no secret/production change.

## 1. Summary
Fixed the Critical/High launch blockers from Manus Phase 8D-2 authenticated browser QA: the
`/ai/gap-analysis/` HTTP 500, the missing `/privacy/` and `/terms/` pages, the repeated Smart
Classification disclaimer, and the landing language-switch / `lang` mismatch. Templates/views/tests only —
**no model, no migration**.

## 2. Manus Findings Addressed
| # | Finding | Status |
|---|---|---|
| 1 | CRITICAL — `/ai/gap-analysis/` HTTP 500 | **Fixed** — safe advisory page, no AI call |
| 2 | CRITICAL — `/privacy/` 404 | **Fixed** — public page added (200) |
| 3 | CRITICAL — `/terms/` 404 | **Fixed** — public page added (200) |
| 4 | HIGH — Smart Classification disclaimer ×8 | **Verified once** locally (was old prod build) + test added |
| 5 | MEDIUM — landing switch stays Arabic | **Fixed** — key strings translated; switch flips content |
| 6 | MEDIUM — landing `lang="en"` with Arabic content | **Fixed** — `lang`/`dir` now consistent with active language |

## 3. Root Causes
- **/ai/gap-analysis/ 500:** the view (`ai_engine.views.run_gap_analysis`) read a non-existent
  `company.applicable_frameworks` attribute **and** triggered a real OpenAI call (`generate_gap_analysis`)
  on GET — both raised for authenticated users (anonymous already got 302 via `@login_required`).
- **Missing legal pages:** `/privacy/` and `/terms/` routes/views/templates never existed.
- **Repeated disclaimer:** on the **current** code the classification disclaimer renders **once**
  (verified by rendering the page: count == 1). The ×8 Manus saw was on the **older production build**
  (`215b0e6`); the present 6A template already shows it once. A regression test now locks "exactly once".
- **Landing language/lang mismatch:** `base.html`'s `<html lang dir>` is dynamic, but the landing body's
  inner `<div>` was hardcoded `dir="rtl"` and the marketing copy was Arabic-only, so switching to English
  flipped `<html lang="en">` while content/direction stayed Arabic/RTL.

## 4. Files Changed
- `ai_engine/views.py` — `run_gap_analysis` → safe `@login_required` advisory render (no AI/network/writes).
- `templates/ai_engine/gap_analysis_advisory.html` (new) — advisory page (links to official reports).
- `core/views.py` — `privacy_policy`, `terms_of_use` views.
- `core/urls.py` — `/privacy/`, `/terms/` routes.
- `templates/core/privacy.html`, `templates/core/terms.html` (new) — Arabic-first, safe legal content.
- `templates/core/landing.html` — dynamic inner `dir`, `{% load i18n %}`, key strings wrapped in `{% trans %}`, footer privacy/terms links.
- `templates/base.html` — footer privacy/terms links.
- `locale/en|ar/LC_MESSAGES/django.po` + `.mo` — English catalog for the new strings.
- `core/tests.py` (+`Phase8D2FixACriticalBlockerTests`, 12) and `ai_engine/tests.py` (gap-analysis test
  updated to the new safe behavior).

## 5. Route Verification (test-client)
`/ai/gap-analysis/` → 302 (anon) / 200 (auth, advisory) — **no 500**; `/privacy/` → 200; `/terms/` → 200;
`/` → 200 (lang/dir consistent, footer legal links); `/login/` → 200; `/get-started/company/` → 200.

## 6. Legal / Trust Safety
No official certification/accreditation claims on the new legal pages or gap-analysis page (asserted).
Both legal pages explicitly state the platform provides **internal readiness/review**, not an official
certificate or government/regulatory accreditation.

## 7. AI / Rule / Auditor Safety
AI remains **advisory** (gap-analysis page says "استشاري … لا يُعد قرارًا نهائيًا"); Rule Engine remains
**suggested**; Auditor Verdict remains **internal human review**. No engine/decision logic was changed; the
gap-analysis view no longer performs any AI/decision work at all.

## 8. Tests
```
python manage.py check                  → no issues
python manage.py makemigrations --check → No changes detected
python manage.py test                   → full suite green (see report; 1 obsolete gap-analysis
                                           test updated to the new safe behavior)
```
`Phase8D2FixACriticalBlockerTests` (12): gap-analysis no-500 (anon+auth, advisory); privacy/terms 200;
footer legal links; legal pages no unsafe claims; classification disclaimer exactly once; landing AR
lang/dir; landing EN lang/dir + key string translated; switch returns + persists; no leak; 417-not-334.

## 9. Migrations
**No migrations.** `makemigrations --check --dry-run` → No changes detected.

## 10. Production Safety
No deployment · no SSH · no production migration · no secret change · no production data change.

## 11. Remaining Items for Next Phase (8D-2-FIX-B)
- Company user can register auditor and session switches (role separation).
- Controls library filters returning empty.
- Classification "Cloud Services only" → "No results yet".
- Activated auditor test account + assigned company file for final auditor-verdict QA.
- Full English translation of the remaining landing marketing prose (currently Arabic-first; key
  above-the-fold strings translated).

## 12. Final Status
**GO — ready for deploy.** All four Critical/High blockers fixed, safe wording preserved, full suite green,
no migration.

## 13. Recommended Next Phase
**Phase 8D-2-DEPLOY-A — Deploy Critical Manus Blocker Fixes** (push + deploy via the no-migration runbook /
smart-deploy guard once SSH access is available), then **Phase 8D-2-FIX-B** for the remaining items above.
