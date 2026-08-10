# 1SaudiCyber — UAT Acceptance Checklist

> **UAT only — do not use in production.** Mark each item Pass / Fail / N/A.

## Functional
- [ ] Public landing loads Arabic-first / RTL with the 1SaudiCyber brand
- [ ] Company registration works (3-step stepper)
- [ ] Onboarding works and reaches the journey dashboard
- [ ] Workflow stepper shows all 13 stages (grouped) + next action
- [ ] Intake save works
- [ ] Framework applicability review works
- [ ] Framework scope approval works (staff)
- [ ] Control plan generation works (staff)
- [ ] Evidence checklist generation works (staff)
- [ ] Evidence Upload v2 works (checksum recorded)
- [ ] Advisory AI analysis runs and is clearly advisory only
- [ ] Subscription gate blocks report access when inactive
- [ ] Manual subscription activation unlocks reports
- [ ] CSV export works (subscribed)
- [ ] XLSX export works (subscribed)
- [ ] Auditor registration works (status pending_review)
- [ ] Auditor admin activation works (status active)
- [ ] Company assigns file to a platform auditor (subscribed)
- [ ] Auditor accepts and views read-only context
- [ ] External auditor option: export + manual off-platform share (no share links — expected)

## Security
- [ ] Anonymous users are redirected from protected pages to login
- [ ] Non-staff cannot perform staff-only actions (generate scope/plan/checklist/assessments, trigger analysis)
- [ ] Cross-company object access is denied (company and auditor sides)
- [ ] Unsubscribed company cannot download/export reports
- [ ] Unsubscribed company cannot assign a platform auditor
- [ ] AI never sets a compliance decision; ControlAssessment stays staff-only
- [ ] Assigned auditor cannot change ControlAssessment

## Platform / quality
- [ ] Docker healthcheck `/healthz/` returns `{"status":"ok"}`
- [ ] `python manage.py check` clean
- [ ] `python manage.py makemigrations --check --dry-run` → no changes
- [ ] Full test suite passes
- [ ] No secrets, `.env`, `db.sqlite3`, or media uploads committed

## Content correctness
- [ ] Official controls shown as 417 (NCA ECC 108 / NCA 231 / Aramco 92 / SABIC 94)
- [ ] Legacy 334 not shown as a current official count
- [ ] No certification-granting claims in public copy
