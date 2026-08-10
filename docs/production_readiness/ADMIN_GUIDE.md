# CyberTrust KSA — Admin Guide

**Audience:** platform administrators / staff. **Status:** Complete for MVP scope.

## Admin responsibilities
- Maintain the official control library (seed/verify), companies, and staff accounts.
- Drive the staff-only workflow steps for a company through to assessable state.
- Keep secrets and the database out of version control (see SECURITY report).

## Seeding / official control library
- Official datasets live in `compliance/data/official_controls/*.yaml` and are the **source of truth**.
- Relevant management commands (run with the project venv, e.g. `python manage.py <cmd>`):
  - `seed_framework_versions` — create `FrameworkVersion` / `SourceDocument` records (incl. the legacy 334 bootstrap).
  - `import_official_controls` / `import_official_controls_pilot` — load official YAML controls.
  - `validate_official_control_dataset` — read-only validation/dry-run of a dataset.
  - `seed_all_controls` — legacy 334 bridge seeding (legacy only; not the official authority).
- **Official total: 417** (Aramco 92, SABIC 94, ECC 108, CSCC 32, OSMACC 15, TCC 21, CCC 55). See `OFFICIAL_CONTROL_LIBRARY_STATUS.md`.

## Framework approval actions (staff-only)
- Review proposed `CompanyFrameworkScope` rows on the framework review page.
- **Approve** or **reject** a scope. Approval is what unlocks the control plan for that framework.

## Control plan generation (staff-only)
- For an **approved** scope, generate the control applicability plan
  (`ControlApplicabilityResult`) over **official controls only** (legacy excluded).

## Evidence checklist generation (staff-only)
- Generate `EvidenceRequirement` templates (official controls) and the company's
  `EvidenceChecklistItem` plan. This is planning only — no uploads happen here.

## User / company management assumptions
- A `User` belongs to at most one `Company` (`user.company`); all workflow data is scoped to it.
- Staff/auditor capability is `user.is_staff` (role `auditor` also surfaces the auditor portal link).
- Company users self-register and complete intake; admins provision staff/auditor accounts.

## Staff-only actions (summary)
Generate scopes/approval · generate control plan · generate evidence checklist ·
trigger advisory analysis · generate assessments · update `ControlAssessment`.
All are blocked for non-staff (enforced in views; covered by tests).

## What must NOT be done manually
- Do **not** hand-edit `ControlAssessment` statuses outside the auditor review flow.
- Do **not** treat AI analysis as a compliance decision.
- Do **not** use the legacy 334 Excel as an official source.
- Do **not** create `CompanyControl` for the new pipeline (it is legacy — see below).
- Do **not** import OTCC/DCC or run OCR into the official library in this MVP.
- Do **not** commit `db.sqlite3` or `.env`.

## Legacy model warnings
- **`CompanyControl` is legacy.** The new CyberTrust pipeline does **not** use it for reporting or assessments.
- **Legacy evidence upload** (`upload_evidence` → `Evidence`) remains for backward compatibility only.
- **New pipeline** uses **`EvidenceSubmission`** (Upload v2) linked to checklist items, plus `EvidenceAnalysisResult` and `ControlAssessment`.
