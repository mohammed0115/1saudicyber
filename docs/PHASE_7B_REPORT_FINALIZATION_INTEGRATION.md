# Phase 7B — Report Finalization Integration

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. Internal package
> `cybertrust_ksa` (technical-only).

**Status:** Local-only. Not deployed to production.

> This phase connects auditor verdicts to internal report outputs.
> This phase does **not** issue certificates.
> This phase does **not** claim official accreditation.
> This phase does **not** rewrite report calculations beyond safe verdict integration.

## What was integrated
Connected the human **Auditor Final Verdict** workflow (Phase 6F) to the report layer via a new,
read-only **internal auditor-reviewed report** that aggregates persisted `AuditorFinalVerdict` records.
The existing reports and subscription gate are untouched; this is an additive report view + a journey
signal change.

## What "finalization" means here
"Finalization" = **surfacing the human auditor verdicts in a report view** — counts, per-status
distribution, and per-control rows. It is an **internal review report**, explicitly **not** an official
certificate or accreditation, and it does **not** recompute or rewrite the existing compliance/report
calculations.

## Integration strategy
**Option B (separate internal report page) + a card on the existing reports index.** The existing report
pages/exports were left intact to avoid risk. New page: **`/compliance/reports/auditor-reviewed/`**,
linked from `reports_index` (subscribed view).

## Report summary service
- **Location:** [compliance/report_finalization.py](../compliance/report_finalization.py) →
  `build_auditor_reviewed_report(company) -> AuditorReviewedReport`.
- **Produces:** total submissions, reviewed vs pending counts, status counts (raw + Arabic-labelled),
  framework_type counts, latest reviewed_at, and per-verdict rows (control id/title, framework,
  rule-engine suggestion label, verdict status + Arabic label, confidence, rationale **excerpt** (≤200
  chars), required-actions count, reviewed_at, reviewer display label, submission id).
- **Intentionally excluded:** raw file path, secrets, full extracted evidence text, raw AI response,
  official-certification wording.
- Read-only: never updates `ControlAssessment` / `CompanyControl` / report calculations; no AI/network.
  Deterministic (tested).

## Status mapping
Reuses the `AuditorFinalVerdict` Arabic labels: NCA `final_c/pc/nc/na` → "متوافق/جزئيًا/غير متوافق/غير
منطبق (بعد مراجعة المدقق)"; Aramco/SABIC `final_compliance/noncompliance/not_applicable` →
"امتثال/عدم امتثال/غير منطبق (بعد مراجعة المدقق)"; shared `needs_more_evidence` → "بحاجة إلى أدلة إضافية".
Never displayed as an official certificate.

## UI integration
The page shows: title "تقرير مراجعة امتثال داخلي", "ملخص قرارات المدقق", the required disclaimer
**"هذا التقرير يعرض نتائج مراجعة داخلية داخل المنصة ولا يُعد شهادة امتثال رسمية أو اعتمادًا من أي جهة."**,
summary cards (إجمالي الأدلة / تمت مراجعتها / بانتظار المدقق / آخر مراجعة), the status distribution, and a
"تفاصيل القرارات" table with permission-safe links to each submission's auditor-verdict page. Empty state:
"لا توجد قرارات مدقق نهائية بعد. يرجى إكمال مراجعة الأدلة أولًا." Touched strings `{% trans %}` + English
catalog. No certification/accreditation wording; no file path.

## Subscription / report gate behavior
The new page reuses the **existing** `_require_full_reports` gate (same as other report views): an
unsubscribed company is shown the subscription-required page, not the report. Staff/superuser behavior
follows the existing `can_view_full_reports` pattern (unchanged). The gate was not weakened.

## Journey integration
The journey **Reports** step (kind `gated`) now completes only when **an active subscription AND a
recorded `AuditorFinalVerdict`** exist (the auditor-reviewed report is available). No subscription →
`locked`; subscription but no verdict → not completed (needs_action/current); both → `completed`.
**Monitoring** is unchanged; no certification step is introduced.

## Security / tenant isolation
Anonymous → 302 `/login`. The report is company-scoped (`request.user.company`) and aggregates only that
company's verdicts; another company's rows never appear (tested). Subscription gate preserved. Row links
point to the per-submission auditor-verdict page, which independently enforces tenant/role access.
Assigned-auditor report access follows the existing per-page access pattern (not broadened here).

## Tests run
- `ReportFinalizationServiceTests` (6): counts, NCA + Aramco status/framework counts, excludes raw
  text/paths, no ControlAssessment/CompanyControl writes, deterministic.
- `ReportFinalizationUITests` (5): empty state + disclaimer, rows after verdict, no certification/334/path
  (and disclaimer present), subscription gate preserved, English mode.
- `ReportFinalizationJourneyTests` (4): reports locked without subscription, not completed with
  subscription but no verdict, completed with both, monitoring unchanged.
- `ReportFinalizationSecurityTests` (3): anonymous redirect, company sees only own rows, verdict still not
  a certificate.
- `manage.py check` clean; `makemigrations --check --dry-run` clean (no model); full suite green.

## Known limitations
- **No official certification / accreditation** (by design).
- Report is a **view/summary**; it does not recompute the existing executive/gap/evidence-matrix reports,
  and verdicts are not yet merged into those legacy reports or exports (export integration deferred).
- No PDF/Excel export of the auditor-reviewed report this phase (could reuse the existing export pattern
  in a later phase).
- Browser smoke deferred (test-client used).

## Out of scope (confirmed not implemented)
Certification issuance, official accreditation claim, payment, external monitoring connectors, SIEM/cloud/
scanner integration, email/SMS/WhatsApp alerting, marketplace pricing, auditor payouts, chat/messaging,
external share links, frontend replacement, production deployment, destructive migration, secrets/`.env`.
