# CyberTrust KSA — Auditor Guide

**Audience:** auditors / staff reviewers. **Status:** Complete for MVP scope.

## Core principle
**The final compliance decision belongs to the auditor.** AI analysis is advisory input only.

## Using the evidence checklist
- The `EvidenceChecklistItem` plan lists the evidence expected for each applicable official control.
- Company users upload evidence per item (Evidence Upload v2 → `EvidenceSubmission`), with a
  recorded SHA-256 checksum, version, and validated file type/size.

## Reviewing evidence submissions
- Open a submission to see its metadata and any attached advisory analysis.
- Submissions carry a status (e.g. `pending_review`, `accepted`, `rejected`, `needs_reupload`).
- Reviewing evidence informs — but does not auto-set — the control assessment.

## What AI advisory analysis means
- `EvidenceAnalysisResult` provides a **summary, a requirement-match hint, and potential gaps**.
- It is generated only when a staff user triggers it; it is **advisory**.

## What AI must NOT be treated as
- It is **not** a compliance decision, **not** an accept/reject of evidence, and **not** a
  source of truth. It never creates or updates a `ControlAssessment` and never sets a compliant status.

## Creating / updating a ControlAssessment
- `ControlAssessment` rows are generated (by staff) as `not_reviewed` for applicable official controls.
- The auditor opens an assessment and records the decision via the review form
  (auditor-only to submit). This sets the reviewer and review timestamp.

## Assessment statuses
| Status | Meaning |
|---|---|
| `not_reviewed` | No auditor decision yet (never counted as compliant). |
| `compliant` | Control satisfied. |
| `partially_compliant` | Partially satisfied. |
| `non_compliant` | Not satisfied. |
| `not_applicable` | Out of scope for this company. |
| `needs_more_evidence` | Decision pending additional evidence. |

## Remediation fields
- `remediation_required` (flag), `remediation_plan` (text), `remediation_due_date`.
- Optional `score`, `risk_level` (low/medium/high/critical), `confidence_level` (low/medium/high), `auditor_notes`.

## Reports and gap analysis
- **Executive summary** — counts by assessment status, completion %, compliance %, evidence coverage.
- **Gap analysis** — per-framework breakdown of gaps (non/partial/needs-evidence/unreviewed).
- **Evidence matrix** — per-control evidence + latest submission/AI/assessment status; CSV/XLSX export.
- Reports are **read-only**, derive from `ControlAssessment` status only, exclude legacy controls,
  and **never** count unreviewed controls as compliant.
