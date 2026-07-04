# PILOT-HOTFIX-B — Admin, Auth, Password Reset, Forms + Evidence Blocker

Local-only hotfix. No deploy, no push, no payment/Moyasar changes, no real keys, no
control-count changes, AI stays advisory. Owner: Get Solution Company.

## What was fixed

| # | Issue | Fix |
|---|-------|-----|
| A | Django admin unbranded; User password shown as raw editable hash | Branded site header/title/index; `UserAdmin` now subclasses Django's `UserAdmin` → password via `ReadOnlyPasswordHashField` (change-password link, never raw). `mfa_secret` excluded from all fieldsets. Registered missing `ControlGapAssessment`, `CompanyCRMProfile`, `CompanyCRMNote`. |
| B | platform-admin lacked official-data visibility | Added **Official data health** panel (Framework / FrameworkVersion / Control counts) with warnings: empty → "No official controls loaded"; small → "Pilot controls loaded / full 417 not loaded". Staff-only, no secrets. |
| C | Login failure silent; error leaked to other pages | Failed login now renders an **inline** error on `/login/` via template context (not global `messages`), preserves the email, never echoes the password. No cross-page leak. |
| D | Password reset looked amateur (`form.as_p`) | Redesigned all four reset pages: centered card, bilingual, responsive, field-level errors, safe "if the account exists" wording (no user enumeration). |
| E | No reusable form design | Added `components/auth_form_styles.html` + `components/form_field.html`; applied to login + reset flow. |
| F | Registration wizard collapsed to all steps on step-3 error | Server computes the errored step; template marks only that step `active` (drops the `js-off` show-all fallback on error) + a persistent submit; JS lands on the errored step. Password never re-rendered. |
| G | Classification disclaimer repeated | Consolidated to a single advisory line ("advisory only, not a final decision, not an official certification"). Added a safe "framework data not loaded" guard so intake/applicability never 500. |
| H | Staff/auditor saw company nav | Role-gated `base.html` nav: staff → Get Solution console links, auditor → auditor portal, company → compliance journey. Backend guards unchanged. |
| I | `/compliance/` and `/company/` returned 404 | Added safe redirects (`/compliance/` → guarded dashboard; `/company/` → main dashboard). Anonymous flows through the existing login guard. |
| — | **Evidence upload 500 + View 404 (pilot blocker)** | See "Evidence blocker" below. |
| — | Template comment leakage concern | Removed all implementation/phase `{# … #}` comments from templates. |

## Evidence blocker — root cause & fix

Root cause (from server diagnosis): the pilot company had framework **scopes that were
not approved**, so `generate_control_applicability_plan` produced 0 controls and
`generate_evidence_checklist` produced **0 `EvidenceChecklistItem`**. With an empty
checklist there was nothing valid to upload against, and the flow could error.

Fixes:
- **Upload can never 500**: `evidence_upload_v2` wraps file save + hashing in `try/except`
  → safe bilingual message + redirect; auditing/status updates are best-effort and never
  crash the response. An invalid/stale checklist item id → safe redirect (already).
- **Approval now chains generation**: approving a framework scope (`approve_scope`, staff)
  now generates the **control plan + evidence checklist** in one step (best-effort), so an
  approved company is never stranded with 0 items.
- **Clear empty states** on the evidence page:
  - No scopes → "No evidence checklist has been generated yet. Complete Smart Classification first."
  - Scopes pending approval → "Framework scope is pending approval. Evidence checklist will be available after approval."
- **View links** only render for existing submissions and use `EvidenceSubmission.id`
  with `compliance:evidence_submission_detail` (verified).
- **Tenant isolation**: own evidence detail → 200; other company / stale id → denied
  safely (302 redirect, no data leak, never 500).

## Admin coverage map — Django Admin vs platform-admin

**Django Admin (`/admin/`, superuser/staff):** low-level record management + data health
for Get Solution engineers. Registered: `User` (safe password), `Company`, compliance
(`Framework`, `FrameworkVersion`, `Control`, `ControlVersion`, `ControlApplicabilityTag`,
`CompanyFrameworkScope`, `FrameworkApplicabilityResult`, `ControlApplicabilityResult`,
`EvidenceRequirement`, `EvidenceChecklistItem`, `EvidenceSubmission`, `EvidenceTextExtraction`,
`EvidenceAnalysisResult`, `EvidenceAIAnalysis`, `EvidenceRuleEvaluation`, `ControlAssessment`,
`ControlGapAssessment`, `AuditorFinalVerdict`, …), `RiskItem`, `RemediationTask`, billing
(`Plan`, `CompanySubscription`, `Payment`), auditors (`AuditorProfile`, `AuditorAssignment`,
`CompanyCRMProfile`, `CompanyCRMNote`), monitoring models.

**platform-admin (`/platform-admin/`, staff/superuser):** the **safe business console** —
companies, users/linking, auditor approval, subscription/payment summaries, feature/usage,
evidence/gap/risk/report summaries, CRM notes/timeline, and official data health. Read-only
selectors + POST-only write actions; never a raw CRUD copy of Django Admin.

**Intentionally Django-Admin-only:** raw model CRUD, permissions/groups, low-level fixes.
**Intentionally platform-admin-only:** business operations, CRM notes/follow-up (never
visible to company/auditor users), auditor approval workflow with reasons.
**Intentionally NOT registered in Django Admin:** `EmailOTP` / verification tokens (contain
one-time secrets — never surfaced). Webhook/Moyasar secrets live only in env, never in admin.

## Security notes
- User password is a read-only hash field with a change-password link (no raw edit).
- `mfa_secret`, OTP codes, reset tokens, Moyasar secret, and env values are never shown in
  admin, platform-admin, or any template.
- Tenant isolation preserved across evidence/detail/scope/upload.
- CSRF preserved everywhere except the external Moyasar webhook (unchanged this hotfix).
- No official certification/accreditation wording introduced (advisory framing only).

## Retest checklist (Manus / QA)
- [ ] `/admin/` shows "Get Solution Company — 1SaudiCyber Admin"; a User's password is not an editable hash field.
- [ ] Wrong login shows an inline error on `/login/`; the error does NOT appear on `/password-reset/`, `/platform-admin/`, `/get-started/`.
- [ ] Password reset pages look professional; unknown + known email both reach the same safe "if the account exists" page.
- [ ] Registration step-3 error keeps you on step 3 (not all steps collapsed); password not pre-filled.
- [ ] Smart Classification disclaimer appears once.
- [ ] Company with pending scope sees "pending approval"; after staff approves the scope, the evidence checklist appears and upload works (302, no 500).
- [ ] Own evidence detail = 200; another company's evidence = denied (no 200, no crash).
- [ ] platform-admin shows official data health (Framework/Version/Control counts) with the pilot/empty warning; non-staff and auditor are denied.
- [ ] Staff nav shows the Get Solution console, not the company journey; company nav shows no platform-admin links.
- [ ] `/compliance/` and `/company/` redirect safely (no 404/500).

## Deferred / notes
- **Evidence detail denial is a non-enumerable 404** (`get_object_or_404` scoped to the
  user's company). Other-company **and** unknown ids both return 404 — never 200, never a
  crash, never revealing existence. Anonymous users hit `@login_required` first (302 → login).
  Existing tenant tests were realigned from 302 to 404 to match this contract.
- **Checklist generation stays staff-driven** (existing tests lock non-staff out). Companies
  are unblocked via the approve→chain generation + clear pending/empty guidance rather than
  self-service generation.
