# CyberTrust KSA — User Journey

**Status:** Complete (read-only journey + guidance).

## End-to-end flow
1. **Login** — authenticated access (`@login_required` on every workflow page).
2. **Intake profile** (`compliance:intake`) — company answers classification questions
   (`CompanyIntakeProfile`); drives framework applicability.
3. **Framework review** (`compliance:applicability_review`) — see deterministic
   `FrameworkApplicabilityResult` and proposed scopes.
4. **Framework approval / scope** — staff/auditor approve or reject `CompanyFrameworkScope`.
5. **Control plan** (`compliance:control_plan`) — `ControlApplicabilityResult` over **official** controls.
6. **Evidence checklist** (`compliance:evidence_checklist`) — `EvidenceChecklistItem` tasks.
7. **Evidence upload** (`compliance:evidence_upload_v2`) — `EvidenceSubmission` per checklist item.
8. **Advisory analysis** — staff trigger; `EvidenceAnalysisResult` (advisory only).
9. **Auditor assessment** (`compliance:auditor_review_queue` / detail) — auditor sets `ControlAssessment`.
10. **Reports** (`compliance:reports_index`) — read-only executive summary, gap analysis, evidence matrix, exports.

## What normal company users can do
- View their own company's intake, framework review, control plan, evidence checklist, journey dashboard, and reports.
- Upload evidence (`EvidenceSubmission`) for their own checklist items.
- View their own submissions and any advisory analysis attached to them.
- They **cannot** approve frameworks, generate plans/checklists/assessments, trigger analysis, or set assessments.

## What staff / auditors can do
- All read access above, plus the staff-only actions:
  - Approve / reject framework scopes.
  - Generate the control plan for an approved scope.
  - Generate the evidence checklist.
  - Trigger advisory AI analysis.
  - Generate `ControlAssessment` rows (as `not_reviewed`).
  - Update a `ControlAssessment` (the final compliance decision).

## What the dashboard shows (`compliance:dashboard`)
- The 9 workflow stages with a status badge each: **not_started / in_progress / completed / needs_attention**.
- A short explanation and a count/metric per stage (e.g. approved frameworks, applicable controls, checklist items, submissions, pending analysis, reviewed vs total assessments).
- Overall progress percentage.
- The single **next recommended action** with a direct link.
- Read-only: rendering the dashboard never writes data and only ever shows the requesting user's company.

## Next-step logic (deterministic)
The next action is decided by a fixed ladder gating on record existence (never on AI output):
1. No intake → **Complete intake profile**
2. No approved scope → **Review and approve applicable frameworks**
3. No control plan → **Generate control plan**
4. No checklist → **Generate evidence checklist**
5. No submissions → **Upload evidence**
6. No analysis → **Run advisory analysis**
7. No assessments → **Start auditor review**
8. Otherwise → **View reports**

## Empty-state behavior
Each early-stage page shows a helpful banner with a safe next-step link when there is no data yet:
- **Control Plan:** "No approved frameworks yet. Start with framework review." → framework review.
- **Evidence Checklist:** "No checklist items yet. Generate checklist after control plan." → control plan.
- **Auditor Review:** "No assessments yet. Generate assessments from approved official controls." → control plan.
- **Reports:** "Reports will be meaningful after auditor assessments are created." → auditor review.
