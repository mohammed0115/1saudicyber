# Prompt 12 — Auditor Portal Repair

Repair Auditor Portal according to SRS FR-009.

Important:
Auditor independence must be protected.
The platform must not force the auditor to accept AI judgment.

Auditor can:
- login separately
- view assigned companies
- view assessments
- review each control
- view original evidence
- view extracted text
- view AI analysis
- view system rule status
- add notes
- override status
- request additional evidence
- mark control verified/rejected
- complete final report
- digitally sign report or use typed sign-off in MVP

Create/repair:
- AuditorProfile
- AuditorAssignment
- AuditorControlReview
- AuditorEvidenceRequest
- AuditReport
- auditor portal views/templates/APIs

For every control show:
- AI Suggested Status
- Rule Engine Status
- Auditor Final Status
- Evidence files
- Notes
- Findings

Acceptance criteria:
- Auditor override does not delete AI/system status.
- Company can respond to additional evidence request.
- Audit progress is tracked.
- Final report uses auditor_final_status.
- Tests cover auditor assignment and override.
