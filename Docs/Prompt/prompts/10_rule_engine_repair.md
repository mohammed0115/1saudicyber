# Prompt 10 — Rule Engine Repair

Build the Rule Engine.

Purpose:
Convert evidence, AI suggestions, and framework rules into system status.

Do not let AI directly update final compliance status.

For NCA:
Allowed statuses:
- C = Compliant
- PC = Partially Compliant
- NC = Non-Compliant
- N/A = Not Applicable

For Aramco/SACS-002:
Report output uses:
- Compliance
- Noncompliance

Internally, support:
- compliant
- partially_compliant
- non_compliant
- insufficient_evidence
- not_applicable
- needs_review

Mapping:
- NCA compliant → C
- NCA partially_compliant → PC
- NCA non_compliant / insufficient_evidence → NC
- NCA not_applicable → N/A
- Aramco compliant → Compliance
- Aramco partial/non_compliant/insufficient_evidence → Noncompliance unless auditor overrides

Rule inputs:
- required evidence exists?
- extracted text exists?
- AI confidence threshold met?
- missing mandatory elements?
- document expired?
- implementation evidence present?
- applicability result?

Create:
- rule_engine/services.py
- evaluate_control_result()
- evaluate_assessment()
- score calculation service

Acceptance criteria:
- Rule Engine updates system_status only.
- Auditor final_status remains separate.
- Scores are deterministic.
- N/A excluded from scoring.
- Tests cover NCA and Aramco status mapping.
