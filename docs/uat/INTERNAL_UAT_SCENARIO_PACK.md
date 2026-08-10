# 1SaudiCyber — Internal UAT Scenario Pack

**Public brand/domain:** 1SaudiCyber — cyber-5.com. **Internal package:** `cybertrust_ksa` (unchanged).
**Status:** Ready for internal UAT/demo. **Not** a production go-live.

> All credentials in this pack are **UAT only — do not use in production.**

## Purpose
A repeatable internal walkthrough that exercises the full 1SaudiCyber workflow end to end:
registration → onboarding → intake → frameworks → control plan → evidence → advisory analysis →
auditor review → subscription gate → reports/exports → platform auditor assignment, plus security checks.

## How to prepare the environment
1. Local app (dev): `python manage.py runserver 0.0.0.0:9999` (or Docker per the runbook).
2. Optional sample data: `python manage.py seed_uat_demo_data --dry-run` then `--apply` (see `UAT_SAMPLE_DATA.md`).
3. Activate subscription for report scenarios: `python manage.py activate_company_subscription --company-id <id> --plan-name "UAT Plan" --days 30` (or seed with `--subscribe`).
4. Activate the demo auditor: Django admin → Auditor profiles → set status **active** (the seed sets it active already).

## Scenario index
| ID | Scenario | File |
|----|----------|------|
| A | Company self-service journey | `COMPANY_WORKFLOW_UAT.md` |
| B | Subscription gate | `SUBSCRIPTION_REPORT_GATING_UAT.md` |
| C | Auditor assignment | `AUDITOR_ASSIGNMENT_UAT.md` |
| D | External auditor option | `AUDITOR_ASSIGNMENT_UAT.md` (Scenario D) |
| E | Security quick checks | `UAT_ACCEPTANCE_CHECKLIST.md` (Security section) |

## Demo facilitation
- Run `FINAL_DEMO_SCRIPT.md` top-to-bottom for a clean ~15–20 minute demo.
- Tick `UAT_ACCEPTANCE_CHECKLIST.md` as you go (pass/fail).
- Capture any defects against `KNOWN_LIMITATIONS_BEFORE_PRODUCTION.md` (known vs new).

## Guardrails validated during UAT
- AI analysis is **advisory only** (never sets a compliance decision).
- Reports/exports and platform-auditor assignment require an **active subscription**.
- `ControlAssessment` is auditor/staff-driven only; assigned auditors get **read-only** context.
- Tenant isolation: a company/auditor only ever sees its own data.
- Official control library = **417** controls (NCA ECC 108, NCA total 231, Aramco 92, SABIC 94); legacy 334 is not an official source; OTCC/DCC are backlog.
