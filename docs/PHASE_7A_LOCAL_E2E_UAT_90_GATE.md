# Phase 7A — Local End-to-End UAT 90% Gate

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. Internal package
> `cybertrust_ksa` (technical-only).

**Purpose:** Verify that the local platform can complete a realistic compliance-review journey — from
company setup to a human auditor verdict — on the current codebase, and decide the local 90% readiness gate.

## Local environment
- Django dev environment, SQLite test DB, `.venv` interpreter. No production, no push, no real network.
- AI Evidence Analyzer exercised via an **injected fake provider** (no OpenAI calls).
- **Commit tested:** `794fe0f` (Phase 6F) — branch `cybertrust-execution`. UAT tests/docs added on top.

## Test data used
Safe generated data only (no customer data): factory companies, intake profiles with intake signals
(cloud / remote work / social media), generated evidence files (TXT with control-related language; a tiny
PNG for the image-only case), staff and assigned-auditor users. All created inside the test DB.

## Scenarios executed & results
| # | Scenario | Method | Result |
|---|---|---|---|
| Baseline | check / makemigrations / migrations / full suite | manage.py | ✅ PASS |
| Count | Official total 417, no legacy 334 in UI | engine + template grep | ✅ PASS |
| A | Company profile → Smart Classification → Applicability + i18n | test-client + service | ✅ PASS |
| B | Evidence upload → extraction → AI advisory (fake) → rule engine → verdict | end-to-end test | ✅ PASS |
| B-Case2 | Image-only evidence → no_text → AI skipped → rule insufficient_data | test | ✅ PASS |
| B-Case3 | Missing AI provider → skipped safely (no crash) | test | ✅ PASS |
| C | Rule = "suggested … بانتظار مراجعة المدقق"; verdict = internal review wording; permissions | test | ✅ PASS |
| D | Reports load/gated; **not** auto-finalized by verdict | test | ✅ PASS (finalization deferred) |
| E | Monitoring continuous route renders/redirects; no connector claims | test + grep | ✅ PASS (foundation only) |
| F | Anonymous redirect; cross-company blocked across extraction/AI/rule/verdict; company can't submit verdict; GET run→405 | test | ✅ PASS |
| G | Arabic RTL nav, language switcher, English mode core pages; no forbidden wording | test + grep | ✅ PASS |

## Screenshots index
Browser smoke **deferred**; Django test-client UAT was used instead (no Playwright/LiveServer browser
tooling provisioned in this environment). Page render is verified via test-client HTTP 200 + content
assertions on `/compliance/classification/`, `/compliance/applicability/`, the per-submission
extraction/AI/rule/verdict pages, and `/monitoring/continuous/`.

## Pass/fail table (gate)
All executed scenarios PASS. Full automated suite green (see Management Summary / final report for the
exact count). No blocking bugs (see `PHASE_7A_UAT_BUGS_FOUND.md`).

## Readiness score (out of 100)
| Area | Score | Note |
|---|---|---|
| Company onboarding/profile/classification | 10 | works end-to-end |
| Applicability engine | 10 | deterministic preview, 417 counts |
| Evidence upload | 10 | existing v2 flow |
| Text extraction truthfulness | 10 | persisted, gated (6C-FIX-A) |
| AI advisory analyzer | 9 | gated + mockable; real provider key not wired locally |
| Rule engine suggested status | 10 | deterministic, suggestion-only |
| Auditor final verdict | 10 | human review recorded, permissioned |
| Reports / subscription behavior | 7 | loads + subscription-gated, **not** tied to verdict (deferred) |
| Monitoring foundation | 7 | foundation only; no connectors/scheduling |
| Security / permissions / i18n | 10 | tenant isolation + RTL/bilingual verified |
| **Total** | **93** | |

## Risks
- Verdict → report finalization not connected (a recorded verdict does not change report numbers yet).
- Monitoring is a foundation (no real external checks/scheduling).
- AI provider is structurally ready but not wired to a real key locally (safe `skipped` fallback).

## Deferred items
Production deployment; verdict-to-report finalization; image OCR; external monitoring connectors
(SIEM/cloud/scanner); payment; real AI key/provider production wiring; verdict history.

## Final gate decision
**PASS — Local 90% Gate** (score 93/100). The full local chain
*Company → Classification → Applicability → Evidence → Extraction → AI Advisory → Rule Engine → Auditor
Verdict* completes on the current codebase, with truthful statuses and safe wording.
