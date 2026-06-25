# Phase 5B — Continuous Monitoring Foundation

**Public brand:** 1SaudiCyber — 1saudicyber.com · **Internal package:** `cybertrust_ksa` (unchanged).

## What was added
An **internal, deterministic** continuous-monitoring foundation in the existing `monitoring` app —
data model, a service layer, a management command, read-only company/auditor UI surfaces, a company
dashboard card, and Django admin. It helps answer: which controls need periodic review, which are
overdue/stale, which checks failed or need manual review, and the company's monitoring status.

It is **not** external-integration monitoring: no SIEM/cloud/vulnerability connectors, no
email/SMS/WhatsApp alerts, no AI/LLM, no external network calls.

## Data model (additive — `monitoring/0002`)
- **MonitoringCheck** — a recurring check for a company (optional `framework_version`/`control`/
  `control_assessment` links). `check_type` ∈ {evidence_freshness, remediation_overdue, risk_review,
  manual_review, policy_review, control_status_review}; `frequency` ∈ {daily, weekly, monthly,
  quarterly, semi_annual, annual}; `status` ∈ {active, paused, archived}; `last_run_at`, `next_run_at`,
  `last_result` ∈ {pass, fail, needs_review, not_run}; `created_by`.
- **MonitoringRun** — one execution: `status` ∈ {pass, fail, needs_review, error}, `summary`,
  `details`, `evidence_snapshot` (JSON), `started_at`/`finished_at`.
- **MonitoringFinding** — an actionable issue: `severity` ∈ {low, medium, high, critical}, `title`,
  `description`, `recommendation`, `status` ∈ {open, acknowledged, resolved, false_positive},
  optional `related_risk` / `related_remediation_task`.

The legacy monitoring models (ComplianceScore, Alert, MonthlyReport, CertificateTracker) are unchanged.

## Service layer (`monitoring/continuous.py`)
- `calculate_next_run_at(frequency, from_dt)` — deterministic next-run = now + frequency window.
- `run_monitoring_check(check, apply=False, now=None)` — evaluates a check **read-only**; with
  `apply=True` persists a `MonitoringRun` (+ a `MonitoringFinding` on fail/needs_review) and reschedules
  the check. Never touches `ControlAssessment`. Evaluation errors are captured as an `error` run.
- `run_due_monitoring_checks(apply, now, company, check_type, limit)` — runs all due checks; returns
  `{scanned, due, runs_created, findings_created, errors, applied}`.
- `summarize_company_monitoring(company)` — read-only counters for dashboards.
- `auditor_can_view_company_monitoring(user, company)` — active auditor + accepted assignment only.

Evaluation logic (deterministic, internal): remediation_overdue → fail if overdue remediation tasks;
risk_review → needs_review if open high/critical risks; evidence_freshness → needs_review if latest
evidence older than one frequency window (or none); control_status_review → pass if linked assessment
is compliant, else needs_review; manual_review/policy_review → needs_review (human prompt).

## Management command
```bash
python manage.py run_monitoring_checks --dry-run     # default; writes nothing
python manage.py run_monitoring_checks --apply       # creates runs/findings, reschedules
# optional filters:
python manage.py run_monitoring_checks --apply --company-id <id> --check-type risk_review --limit 50
```
Output summarizes: checks scanned, due, runs created, findings created, errors.

## UI / routes (read-only)
- `/monitoring/continuous/` — monitoring overview (counters: active/due/overdue/failed/needs-review,
  open findings, critical-high, last run, next due).
- `/monitoring/checks/` — checks list. `/monitoring/findings/` — findings list.
- `/monitoring/assignment/<id>/` — read-only monitoring summary for an auditor's accepted assignment.
- Company dashboard: an informational **"المراقبة المستمرة"** card (active checks, due now, open
  findings, last result) linking to the overview. Arabic-first, RTL, calm styling.

## Permissions / tenant isolation
- Company users & staff: their own company only (`request.user.company`).
- Assigned auditors: **read-only** for accepted assignments (active auditor); pending/unassigned denied.
- Anonymous: redirected to login. No cross-company leakage (tests verify).

## What this phase does NOT do
No external/SIEM/cloud/vulnerability integrations; no email/SMS/WhatsApp alerts; no AI/LLM; no
`ControlAssessment` decision changes; no report/subscription/auditor-assignment/Risk-Register logic
changes; no OTCC/DCC; no OCR; no upload/frontend rewrite; no destructive migration; no production
deployment; no secrets.

## Next phase recommendations
- **Phase 5C** — Monitoring scheduling (cron/Celery beat) + finding lifecycle actions (acknowledge/
  resolve) and optional creation of risks/remediation tasks from findings.
- Later — opt-in external connectors and notification channels (separate, clearly-scoped phases).
