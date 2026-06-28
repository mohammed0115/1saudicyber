# Manus E2E QA Test Accounts — Activated Auditor Final-Verdict Workflow

This document describes how to prepare a safe, **QA-only** test scenario so a
tester (e.g. Manus) can complete the full *activated auditor → assigned company
file → final auditor verdict* workflow.

> **QA-ONLY.** These fixtures use obviously-fake data, take no payment, and must
> never be used in production with real customer data.

## Quick start (recommended) — management command

```bash
python manage.py seed_manus_e2e_qa --confirm
```

The command is **idempotent** (safe to re-run) and refuses to run without
`--confirm` (or `DJANGO_ALLOW_QA_SEED=1`). It prepares:

- **One company test account** — `qa.company@manus-e2e.test` / `ManusQA-pass-12345`
  (Company `QA Manus E2E Co (TEST)`, CR `QA-MANUS-0001`, QA-marked active
  subscription — *no payment record is created*).
- **One activated auditor account** — `qa.auditor@manus-e2e.test` /
  `ManusQA-pass-12345` (`AuditorProfile.status = 'active'`).
- **An accepted assignment** linking the auditor to the company file
  (`AuditorAssignment.status = 'accepted'`).
- **A company file ready for a verdict** — an approved framework scope, a control
  applicability plan, an evidence checklist, and one evidence submission with
  advisory AI + rule-engine context. The verdict URL is printed on success.

> The evidence submission is only created when the official controls for
> `ARAMCO-SACS-002` are imported in the target environment. If they are not, the
> auditor and assignment are still seeded and usable; import the official control
> library first to enable the verdict step. (The control library / 417-control
> totals are never modified by this command.)

### How the tester completes the verdict

1. Log in as the **activated auditor** account.
2. Open the auditor dashboard → the accepted assignment for the QA company.
3. Open the seeded evidence submission's verdict screen (URL printed by the
   command) and record an internal final verdict.

The auditor verdict is an **internal human review only** — it is not an official
certification or accreditation and does not finalize any external report.

## Manual procedure (if you cannot run the command)

Using the Django admin or shell, create the equivalent records:

1. **Company** — a clearly QA-marked `Company` (e.g. CR `QA-MANUS-0001`).
2. **Company user** — a `User` with `role='company_admin'` linked to that company.
3. **Subscription** — call
   `billing.subscription_access.activate_company_subscription(company, 'QA/TEST …')`
   (manual activation, no payment).
4. **Auditor user** — a `User` with `role='auditor'`.
5. **Auditor profile** — an `AuditorProfile` for that user with `status='active'`,
   `is_available=True`.
6. **Assignment** — an `AuditorAssignment(company=…, auditor=…, status='accepted')`.
7. **Evidence to review** — generate a framework scope → control plan → evidence
   checklist for the company, then create one `EvidenceSubmission` against a
   checklist item. (See `seed_manus_e2e_qa` for the exact, idempotent sequence.)

## Cleanup

All fixtures are namespaced under the `*@manus-e2e.test` emails and CR
`QA-MANUS-0001`, so they are easy to identify and remove from a non-production
environment when QA is finished.
