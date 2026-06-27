# Phase 6E — Rule Engine Suggested Compliance Status

> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. The internal Django
> project package name remains `cybertrust_ksa` (technical-only, intentionally unchanged).

**Status:** Local-only. Not deployed to production.

> This phase produces **suggested** statuses only.
> This phase does **not** produce a final auditor verdict.
> This phase does **not** issue certification.
> This phase does **not** update final reports.

## What was implemented
A local, **deterministic** Rule Engine that combines per-control applicability (6B), persisted text
extraction (6C-FIX-A), and the advisory AI analysis (6D) into a framework-specific **system-suggested,
non-final** compliance status. Every result is explicitly **"حالة نظامية مقترحة — بانتظار مراجعة المدقق"**.
Surfaced as a per-submission preview with a POST run action and wired into the journey wizard. No AI, no
network.

## Status vocabulary
- **NCA frameworks:** `suggested_c` (متوافق مبدئيًا), `suggested_pc` (متوافق جزئيًا مبدئيًا),
  `suggested_nc` (غير متوافق مبدئيًا), `suggested_na` (غير منطبق مبدئيًا), `needs_review` (يحتاج مراجعة),
  `insufficient_data` (بيانات غير كافية).
- **Aramco / SABIC frameworks:** `suggested_compliance` (امتثال مبدئي),
  `suggested_noncompliance` (عدم امتثال مبدئي), `suggested_not_applicable` (غير منطبق مبدئيًا),
  `needs_review`, `insufficient_data`.
- Framework type is derived from the control's framework version code (`NCA-*` → NCA;
  `ARAMCO*`/`SABIC*` → Aramco/SABIC). All statuses are shown with "بانتظار مراجعة المدقق" — never final.

## Input gates / fallback
- No related control → `skipped` ("لا يوجد ضابط مرتبط بهذا الدليل.").
- Control **not applicable** (6B preview) → `suggested_na` / `suggested_not_applicable` (no extraction needed).
- No persisted extracted text (6C gate) → `insufficient_data`.
- Extracted text but **no completed** AI advisory analysis (6D) → `needs_review`.
- Completed AI analysis → status derived from relevance + missing items + confidence.

## Rule logic (deterministic, ordered)
| Condition | NCA | Aramco/SABIC | Confidence |
|---|---|---|---|
| Not applicable | `suggested_na` | `suggested_not_applicable` | 80 |
| No extracted text | `insufficient_data` | `insufficient_data` | 20 |
| Text but no completed AI analysis | `needs_review` | `needs_review` | 40 |
| AI relevance **high** & no missing items | `suggested_c` | `suggested_compliance` | min(ai, 90) |
| AI relevance **medium** OR missing items present | `suggested_pc` | `needs_review` | min(ai, 75) |
| AI relevance **low** | `suggested_nc` | `suggested_noncompliance` | min(ai, 70) |
| AI relevance **unclear** | `needs_review` | `needs_review` | min(ai, 50) |

Branches are evaluated in this order (e.g. high-with-missing falls to the medium/missing branch → partial).

## Persistence decision
**Additive model** `EvidenceRuleEvaluation` (OneToOne → `EvidenceSubmission`): status, suggested_status,
confidence, rationale, rule_signals (JSON), missing_requirements (JSON), framework_type, error_message,
evaluated_at. Migration **`compliance/0014_evidenceruleevaluation.py`** — additive (1 CreateModel, 0
destructive ops). Read-only admin (add disabled). `status` ∈ {completed, skipped, failed}.

## Rule engine service
- **Location:** [compliance/rule_engine.py](../compliance/rule_engine.py).
- `suggest_status_for_submission(submission) -> RuleEvaluationResult` — pure, deterministic, no persistence.
- `evaluate_submission_rules(submission, actor=None)` — upserts one `EvidenceRuleEvaluation` (re-run
  updates, never duplicates); `skipped` (no control) / `failed` (unexpected error, generic message).
- **Never** updates `ControlAssessment` / `CompanyControl` / reports (tested).

## UI integration
- New page **`/compliance/evidence-submissions/<id>/rule-evaluation/`**: "محرك القواعد", the disclaimer
  "هذه نتيجة نظامية مقترحة وليست قرارًا نهائيًا. النتيجة النهائية تعتمد على مراجعة المدقق.", a run/re-run
  button, and (completed) "حالة نظامية مقترحة" + "بانتظار مراجعة المدقق", "مستوى الثقة", "سبب الاقتراح",
  "إشارات القواعد", "العناصر الناقصة".
- POST **`/run-rule-evaluation/`**; linked from submission detail. `{% trans %}` + English catalog.
- No "تم الاعتماد" / "قرار نهائي" / "شهادة" wording; no file path shown.

## Journey integration
The `rule_engine` step (kind `rule_engine`): **completed** only when a persisted `EvidenceRuleEvaluation`
with `status='completed'` exists; **needs_action** when a completed AI advisory analysis exists but no rule
run; **planned** otherwise. Auditor Review and Final Verdict remain not completed.

## Security / tenant isolation
`@login_required`; anonymous → 302 `/login`. Preview + POST filter by `company=request.user.company`;
cross-company → redirect and POST writes nothing (tested). POST-only run action (GET → 405). No file path
leaked, no secrets, no AI/network. Auditor access out of scope (company-user-only).

## Tests run
- `RuleEngineServiceTests` (11): all rule branches (NCA + Aramco/SABIC), insufficient/needs_review/na,
  confidence caps, rerun-no-duplicates, determinism, does-not-touch ControlAssessment/CompanyControl.
- `RuleEngineUITests` (4): page renders, POST run shows suggestion + "بانتظار مراجعة المدقق", no
  final/cert wording + no path, English mode.
- `RuleEngineJourneyTests` (4): planned before AI, needs_action after AI before rule, completed after rule,
  auditor/final-verdict not completed.
- `RuleEngineSecurityTests` (4): anonymous redirect, cross-company view blocked, cross-company POST writes
  nothing, GET run → 405.
- `manage.py check` clean; `makemigrations --check --dry-run` clean after migrate; full suite green.

## Known limitations
Rules are intentionally conservative (e.g. high-with-missing → partial; Aramco/SABIC medium-or-missing →
needs_review). Every output is a suggestion requiring human auditor review; the engine never finalizes.
Depends on upstream extraction + AI advisory results.

## Out of scope (confirmed not implemented)
Auditor Final Verdict, final compliance judgment, certification, CompanyControl generation, OCR, new AI
analysis logic, payment, external connectors, monitoring alerting, report/subscription/auditor/risk/control
decision rewrite, upload rewrite, frontend replacement, production deployment, destructive migration,
secrets/`.env`.
