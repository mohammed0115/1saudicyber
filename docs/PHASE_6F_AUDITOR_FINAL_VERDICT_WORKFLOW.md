# Phase 6F — Auditor Final Verdict Workflow

> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase records a **human reviewer** verdict.
> This phase does **not** issue certification.
> This phase does **not** claim official accreditation.
> This phase does **not** finalize external reports.

## What was implemented
The first phase where a **human-reviewed final verdict** is recorded inside the platform. An authorized
reviewer (staff/superuser, or an assigned active auditor) reviews the full context for an
`EvidenceSubmission` — extracted text, advisory AI analysis, and the rule-engine suggested status — and
records an `AuditorFinalVerdict`. It is an **internal review decision**, explicitly **not** an official
certificate or accreditation.

## Data model / migration
**Additive model** `AuditorFinalVerdict` (OneToOne → `EvidenceSubmission`): reviewer (FK PROTECT),
status, confidence, rationale (required), required_actions (JSON), framework_type,
source_rule_evaluation (FK SET_NULL → `EvidenceRuleEvaluation`), reviewed_at. Migration
**`compliance/0015_auditorfinalverdict.py`** — additive (1 CreateModel, 0 destructive ops). Read-only
admin (add disabled).

## Permission model
- **Staff / superuser** → may submit.
- **Assigned auditor** → may submit when the user has an **active** `AuditorProfile` and an **accepted**
  `AuditorAssignment` to the submission's company (reuses `auditors.services`).
- **Company user (owner)** → may **view** their own submission's verdict; **cannot** submit/edit.
- **Anonymous** → redirected to `/login`.
- **Cross-company** (non-owner, non-staff, non-assigned) → blocked (redirect; nothing written).
Permissions are enforced both in the service (`record_auditor_final_verdict` raises `VerdictError`) and
the view (POST by a company user → error, no write).

## Verdict status vocabulary
- **NCA-style:** `final_c`, `final_pc`, `final_nc`, `final_na`.
- **Aramco / SABIC-style:** `final_compliance`, `final_noncompliance`, `final_not_applicable`.
- **Shared:** `needs_more_evidence`.
Framework type is derived from the control's framework version (reusing the rule-engine helper); a status
from the wrong framework family is rejected. Display labels all read "… (بعد مراجعة المدقق)".

## Verdict service
- **Location:** [compliance/auditor_verdict.py](../compliance/auditor_verdict.py).
- `can_submit_final_verdict(user, submission)`, `can_view_submission_review(user, submission)`,
  `allowed_statuses_for(submission)`, `record_auditor_final_verdict(submission, reviewer, status,
  rationale, confidence=None, required_actions=None)`.
- Validation: permission, framework-valid status, **required rationale**, confidence clamped 0–100,
  required_actions sanitized/capped. **Upserts one verdict per submission** (latest wins) and links the
  current rule evaluation as `source_rule_evaluation`.
- **Never** updates reports, `CompanyControl`, or `ControlAssessment`; no AI/network.

## UI integration
- New page **`/compliance/evidence-submissions/<id>/auditor-verdict/`** (GET review + POST verdict):
  shows the rule-engine **suggestion** (labelled "مقترح — بانتظار مراجعة المدقق"), the **advisory** AI
  result, the extraction summary, the rule rationale, and the current verdict. Authorized reviewers get
  the form (status / سبب القرار / مستوى الثقة / الإجراءات المطلوبة / حفظ قرار المدقق); company users see
  "يمكنك عرض القرار، ولا تملك صلاحية تعديله.". Disclaimer:
  **"هذا القرار يمثل مراجعة داخلية داخل المنصة ولا يُعد شهادة امتثال رسمية."**
- No official-certification wording (no "شهادة رسمية"/"اعتماد رسمي من جهة حكومية"/"معتمد من NCA/أرامكو/سابك");
  no file path shown. `{% trans %}` + English catalog.

## Evidence detail integration
The submission detail page now links the full chain with clear labels: **استخراج النص**,
**التحليل الاستشاري** (advisory), **محرك القواعد (حالة مقترحة)** (suggested), and
**قرار المدقق النهائي (مراجعة بشرية)** (human review).

## Journey integration
- **Auditor Review** step (kind `auditor_review`): `completed` when a recorded `AuditorFinalVerdict`
  exists; `needs_action` when a completed rule evaluation exists but no verdict; `planned` otherwise.
- **Final Verdict** step (label "النتيجة النهائية بعد المراجعة", kind `partial`): `completed` when a
  verdict exists, else `planned`.
- **Reports** step is unchanged (still gated on subscription + reviewed assessments) and remains not
  completed just from a verdict — no report finalization or certification here.

## Security / tenant isolation
Anonymous → 302 `/login`. View access limited to owner company user / staff / assigned auditor;
cross-company → redirect. POST by a company user → error + no write; cross-company POST → no write
(tested). No file path/secrets leaked; no AI/network.

## Tests run
- `AuditorVerdictServiceTests` (9): staff records, assigned auditor records, company user blocked,
  rationale required, invalid status rejected, Aramco vocabulary + cross-framework rejection, confidence
  clamp, rerun-updates-one, no reports/CompanyControl writes.
- `AuditorVerdictUITests` (5): owner read-only message, staff form + POST creates verdict, company POST
  forbidden no-write, no official-cert wording + no path, English mode.
- `AuditorVerdictJourneyTests` (4): auditor_review planned before rule, needs_action after rule,
  auditor_review + final_verdict completed after verdict, reports not completed.
- `AuditorVerdictSecurityTests` (3): anonymous redirect, cross-company view blocked, cross-company POST
  writes nothing.
- `manage.py check` clean; `makemigrations --check --dry-run` clean after migrate; full suite green.

## Known limitations
- Per-submission verdict (OneToOne, latest wins) — no verdict history kept this phase.
- **No certification / official accreditation** and **no report finalization** (deferred): a verdict does
  not change reports, `ControlAssessment`, or `CompanyControl`. The existing ControlAssessment-based
  auditor queue remains separate.
- Assigned-auditor submission requires an active profile + accepted assignment; broader auditor scoping
  (per-control) is future work.

## Out of scope (confirmed not implemented)
Certification issuance, official accreditation claim, report calculation rewrite, CompanyControl
generation, OCR, new AI analysis logic, new Rule Engine logic, payment, external connectors, monitoring
alerting, subscription rewrite, auditor assignment rewrite, Risk Register rewrite, ControlAssessment
destructive rewrite, upload rewrite, frontend replacement, production deployment, destructive migration,
secrets/`.env`.
