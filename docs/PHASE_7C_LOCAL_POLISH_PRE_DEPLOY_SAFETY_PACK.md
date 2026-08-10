# Phase 7C — Local Polish / Pre-Deploy Safety Pack

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. Internal package
> `cybertrust_ksa` (technical-only).

**Status:** Local-only. Not deployed. No push.

> This phase is a verification + regression + documentation pass before any deployment planning.
> No new features, no schema changes, no production deployment.

## What was checked
A full local polish/safety sweep after Phase 7B across the 6A–7B surfaces: baseline technical checks,
route smoke for the whole evidence chain, Arabic/English wording, status-badge meaning, wording-safety
(no certification/accreditation claims, no legacy 334), report safety, journey truthfulness, and
permission/tenant isolation. Result: the local product is clean and internally consistent; **no product
code changes were required** — Phase 7C adds regression tests + documentation only.

## Baseline checks
- `manage.py check` → no issues.
- `makemigrations --check --dry-run` → **No changes detected** (no pending schema drift).
- Full suite green (see final report for the exact count).

## Route smoke result
Verified via the test client (`Phase7CPreDeployPolishTests`):
- Authorized owner → **200** on: dashboard, classification, applicability, reports index,
  auditor-reviewed report, and per-submission extraction / AI analysis / rule evaluation / submission
  detail / auditor verdict. `/monitoring/continuous/` → 200/302.
- Anonymous → **302 `/login`** on every protected page.
- `run-*` actions are POST-only (**GET → 405**). No broken routes / reverse-name mismatches.

## UX / wording polish
Arabic labels are consistent across the chain: التصنيف الذكي · قابلية تطبيق الضوابط · استخراج النص من
الدليل · التحليل الاستشاري للذكاء الاصطناعي · محرك القواعد · حالة نظامية مقترحة · قرار المدقق النهائي ·
تقرير مراجعة امتثال داخلي · بانتظار مراجعة المدقق · مراجعة داخلية داخل المنصة. Status meanings are stable
(مكتمل / يحتاج إجراء / مخطط/planned / مغلق-locked / بانتظار مراجعة المدقق / مقترح / استشاري / مراجعة بشرية).
English mode renders on key pages. No new strings were needed (catalogs unchanged this phase).

## Wording safety result
- **No `334`** as a current total anywhere user-facing; **`417`** remains the official total.
- **No positive certification/accreditation claims** (no "official certification/accreditation",
  "certified by NCA/Aramco/SABIC", "معتمد من …", "اعتماد حكومي", "تم إصدار شهادة", "CyberTrust KSA").
- The only "شهادة/رسمية" occurrences are **negation disclaimers** ("…ولا يُعد شهادة امتثال رسمية…") on the
  auditor-verdict and auditor-reviewed-report pages — present and correct.
- AI = advisory; Rule Engine = suggested ("بانتظار مراجعة المدقق"); Auditor verdict = internal human
  review; Report = internal review report.

## Report safety result
`/compliance/reports/auditor-reviewed/`: subscription gate preserved (`_require_full_reports`); clear
empty state; verdict rows scoped to the owner company only; no raw extracted text, no raw AI response, no
file path; required disclaimer present; clear Arabic status labels. Export merge remains **deferred**.

## Journey consistency result
- Classification → completed when intake/classification available.
- Applicability → completed when intake/control plan available.
- Evidence Upload → completed when a submission exists.
- Text Extraction → completed only with a persisted `extracted` (char_count>0) result.
- AI Analysis → completed only with a persisted `completed` advisory analysis.
- Rule Engine → completed only with a persisted `completed` rule evaluation.
- Auditor Review / Final Verdict → completed only when an `AuditorFinalVerdict` exists.
- Reports → completed only with active subscription **and** a recorded verdict (locked without subscription).
- Monitoring → unchanged (foundation). OCR/connectors/payment/certification are **not** marked completed.

## Permission / tenant isolation result
Anonymous redirected; company A cannot view company B's extraction/AI/rule/verdict/report rows; company
users cannot submit a verdict; staff/superuser and active assigned auditors can submit; `run-*` GET → 405.
Verified by the new regression class plus the existing per-phase suites.

## Tests added/updated
`Phase7CPreDeployPolishTests` (10): chain route smoke (owner 200), anonymous redirects, wording safety on
rule/verdict/report pages, AI advisory wording, full-chain journey completion + monitoring-not-completed,
cross-company blocked across the chain, company-can't-submit-verdict, GET run→405, English-mode key pages,
official total 417 (not 334).

## Migration status
**No migrations** added this phase; `makemigrations --check --dry-run` clean. The local additive
migrations that a future production deploy must apply (all additive, no destructive ops) include:
`compliance 0012_evidencetextextraction`, `0013_evidenceaianalysis`, `0014_evidenceruleevaluation`,
`0015_auditorfinalverdict`, plus the earlier 5A–5B/4x app migrations (risk, monitoring, billing,
auditors, core) if the live server predates them.

## Deferred items
Production deployment; OCR for scanned images/PDFs; external monitoring connectors (SIEM/cloud/scanner);
payment; real AI provider/key production wiring; browser smoke (test-client used instead); report
export/PDF merge of the auditor-reviewed report; auditor verdict history.

## Pre-Deploy Readiness Checklist (before Phase 8A)
```
[x] Confirm local branch clean (cybertrust-execution, clean tree)
[x] Confirm all tests pass (full suite green)
[ ] Confirm migrations list vs production gap (apply additive 0012–0015 + 5A/5B/4x app migrations)
[ ] Confirm backup plan (DB pg_dump + media tar before deploy)
[ ] Confirm environment variables (.env on host: SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, POSTGRES_*, optional OPENAI_API_KEY)
[ ] Confirm static files strategy (collectstatic via entrypoint / WhiteNoise)
[ ] Confirm rollback plan (previous image/release + DB restore)
[ ] Confirm smoke test list (/healthz/, login, journey, classification, applicability, auditor-reviewed report)
[x] Confirm no secrets committed (guard clean; .env/db.sqlite3/media not tracked)
[ ] Confirm user approval before deploy (deployment is a separate, explicitly-authorized step)
```

## Readiness recommendation
Local product is consistent, safe-worded, permission-isolated, and fully test-covered end-to-end.
Recommend proceeding to **Phase 8A — Controlled Production Deployment Plan** (deployment itself remains a
separate, explicitly-authorized action requiring host access).
