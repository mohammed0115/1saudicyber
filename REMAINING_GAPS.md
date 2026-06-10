# REMAINING_GAPS

After the verification-and-repair pass (2026-06-09). The 6 PATCH_NOTES bugs and 2 runtime bugs
are fixed and tested. The items below are **not regressions** — they are gaps against the SRS /
prototype that remain open. None block the critical-patch gate. Ordered by priority.

## Critical / High
1. **Auditor independence not enforced in the Rule Engine.** The principle is honored in data
   shape (separate `ai_verdict` vs `auditor_verdict` fields), but there is **no dedicated Rule
   Engine module** (`evaluate_control_result` / `evaluate_assessment`) per prompt 10. Final
   `CompanyControl.status` is set by the AI pipeline (`status='ai_reviewed'`) rather than a
   deterministic rules layer that maps to NCA C/PC/NC/N-A and Aramco Compliance/Noncompliance.
   *Fix:* add `rule_engine/services.py` producing `system_status`, kept distinct from auditor final.
2. **Tenant isolation is not centrally enforced.** Views read `request.user.company`, but there
   is no object-level permission layer; `control_detail`/`upload_evidence` fetch `Control` by id
   without checking it belongs to the user's company scope. No cross-tenant leakage test exists.
   *Fix:* add a company-scoping mixin/decorator + object-level permission tests (prompt 17).
3. **Aramco/SACS-002 report generator not implemented.** The template structure is confirmed
   (TPC-N, General/Specific requirements, Compliance/Noncompliance, classification block), but
   `dashboard/reports.py` only emits a generic gap-analysis PDF + controls Excel. No NCA-format
   report and no SACS third-party report (prompt 13).

## Medium
4. **Celery/beat unproven end-to-end.** Tasks and schedule exist but require Redis; no eager-mode
   test. Upload falls back to synchronous processing if the broker is unreachable (acceptable),
   but the async path is untested.
5. **SSE stream has no automated test.** `event_stream` generator (`monitoring/views.py`) is
   verified by inspection only.
6. **Applicability engine missing.** No `AssessmentScope` / `ApplicabilityResult`; all controls
   for a targeted framework are attached to the company indiscriminately (`_create_company_control_checklist`).
   N/A-with-justification and Aramco General-vs-Specific applicability (prompt 6) are not modeled.
7. **Classification is AI-only.** `classify_company` calls OpenAI with a deterministic fallback,
   but there is no deterministic rules-first tier or stored `ClassificationHistory`/override
   (prompt 5). With no `OPENAI_API_KEY`, classification degrades to a stub summary.
8. **Right-to-deletion view untested.** `delete_company_data` works but has no test; only the
   `purge_expired_data` command is covered.

## Low / cosmetic
9. **`staticfiles.W004` warning** — `static/.gitkeep` added; warning clears once assets exist.
10. **`db.sqlite3` is committed** to the repo (614 KB, pre-seeded). Fine for a demo, but it ships
    the dev `admin@cybertrust.sa / CyberTrust2024!` credentials from the README — rotate before
    any shared/prod use.
11. **NCA report template not shipped as a file.** Reporting relies on the SRS-described
    C/PC/NC/N-A model; if a formal NCA template is required, source it before building prompt 13.

## Explicitly out of scope this pass (per instructions)
Dashboards, AI engine deepening, monitoring/integrations build-out — deferred until after the
critical-patch gate, which now passes.
