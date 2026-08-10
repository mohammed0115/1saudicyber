# CyberTrust KSA — Current System Audit
> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django project package name remains `cybertrust_ksa` (former internal project name: CyberTrust KSA); it is technical-only and intentionally unchanged.


**Status:** Ready for UAT (after deployment setup) · **Last reviewed:** Phase 3K

## Repository state
- **Branch:** `cybertrust-execution`
- **Latest accepted commits:**
  - Phase 3I — `6a09eb1` — Harden CyberTrust dashboard and user journey
  - Phase 3J — `d88cf7a` — Harden CyberTrust security and tenant isolation
- **Test suite:** 450 tests, all passing (Django test runner).
- **Migrations:** clean — `makemigrations --check --dry-run` reports *No changes detected*.

## Installed apps / modules
| App | Role |
|-----|------|
| `core` | Custom `User`/`Company`, auth, registration, MFA, middleware (CSP, audit log) |
| `compliance` | The CyberTrust workflow engine (intake → reports), official datasets, security helpers |
| `ai_engine` | Advisory AI/classification helpers (assistant only, never a compliance decision) |
| `dashboard` | Role dashboards + the read-only journey overview entry point |
| `auditor_portal` | Auditor-facing review surfaces |
| `monitoring` | Monitoring hub / async evidence task hooks |
| `api` | DRF API surface |

Third-party: `rest_framework`, `corsheaders`, `django_filters`, `whitenoise`.

## Implemented workflow (Complete)
1. **Intake** — `CompanyIntakeProfile`; structured classification answers.
2. **Framework applicability** — deterministic, explainable `FrameworkApplicabilityResult`.
3. **Framework approval / scope** — `CompanyFrameworkScope` (proposed → approved/rejected), staff-approved.
4. **Control plan** — `ControlApplicabilityResult` over **official** controls only.
5. **Evidence checklist** — `EvidenceRequirement` templates → `EvidenceChecklistItem`.
6. **Evidence Upload v2** — `EvidenceSubmission` (checksum, version, type/size validation).
7. **Advisory AI analysis** — `EvidenceAnalysisResult` (advisory only; never decides compliance).
8. **Auditor review / ControlAssessment** — auditor is the only decision-maker.
9. **Reports / gap analysis** — read-only executive summary, gap analysis, evidence matrix, CSV/XLSX exports.
10. **Dashboard journey** — read-only end-to-end status, next-step guidance, empty states.
11. **Security / tenant QA** — auth, tenant isolation/IDOR, staff-only gates, upload safety, advisory containment (450 tests).

## Not included in this MVP (by design / deferred)
- **OTCC official import** — manual review workspace only (47 slots), not an official dataset, not applied.
- **DCC official import** — Blocked pending an official text source or a separately approved OCR-reviewed list.
- **Subcontrol hierarchy** — Backlog (optional `parent_control`/level model); not part of MVP.
- **Production Docker deployment** — Next phase (3L); not implemented.
- **Production secrets setup / server hardening** — Needs configuration (documented in DEPLOYMENT_CHECKLIST.md).
- **Full Arabic/English UI polish** — functional bilingual labels exist; comprehensive UX polish not separately verified.
- **Heavy OCR for PDF/images** — not implemented; advisory analysis is text-based and advisory only.

See `OFFICIAL_CONTROL_LIBRARY_STATUS.md` for control counts and source-of-truth notes.
