# CyberTrust KSA — Security & Tenant Isolation Report

**Status:** Complete (application-layer) · **Needs configuration:** production server hardening.

## Authentication coverage
- Every CyberTrust workflow view is decorated with `@login_required`.
- Anonymous access to core pages, exports, the dashboard, upload v2, auditor update, and analysis
  trigger all redirect to login; anonymous POSTs mutate nothing.

## Tenant isolation / IDOR strategy
- Every company-scoped object is fetched with an explicit `company=request.user.company` filter.
- No view fetches a company-scoped object by primary key alone.
- Object detail/update/upload/analyze/report-by-id endpoints redirect (not 500/leak) when the id
  belongs to another company.
- Verified per resource: control plan, evidence checklist, checklist-item upload, submissions,
  analysis (via submission detail), assessments, framework reports, exports, and dashboard counts.

## Staff-only action strategy
- Generating scopes/approval, generating the control plan, generating the evidence checklist,
  triggering advisory analysis, generating assessments, and updating a `ControlAssessment` all
  require `request.user.is_staff`. Non-staff attempts redirect and produce no state change.

## Upload validation strategy
- `EvidenceSubmissionForm` enforces an allowed-extension whitelist and a max size before any record
  is created; the view cannot bypass it. A SHA-256 checksum and version are recorded per submission.
- Upload v2 never creates legacy `Evidence` or `CompanyControl`.

## Report / export isolation
- Reports and CSV/XLSX exports are built from `request.user.company` only and exclude legacy
  controls. Framework-filtered reports resolve only against the company's **approved** frameworks.

## AI advisory containment
- Analysis is advisory: it never creates/updates a `ControlAssessment` and never sets a compliant
  status. Reports read `ControlAssessment` status only; unreviewed controls are never counted as compliant.

## Secrets safety
- `.gitignore` covers `.env`, `*.env`, and `db.sqlite3`; none are tracked.
- No secrets are written to logs by the workflow code.

## Key helper
- `compliance/security.py` → **`get_company_object_or_none(model, company, **filters)`**: tenant-safe
  single-object lookup that returns `None` for cross-tenant ids or a user without a company.
- `user_is_staff(user)` — staff/auditor gate helper.

## Production warnings (Needs configuration)
The application layer is hardened, but a production deployment must still configure:
- HTTPS / reverse proxy and `SECURE_*` settings.
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, secure cookie flags.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Centralized logging (without secrets), backups/restore, and monitoring.
See `DEPLOYMENT_CHECKLIST.md`.
