# Prompt 07 — Assessment Lifecycle Repair

Repair the assessment lifecycle.

Current project must support multiple assessments per company.
Do not store final control state only on CompanyControl if that prevents historical assessments.

Required concepts:
- Company
- Framework
- Assessment
- AssessmentControlResult
- Evidence
- AIAnalysis
- AuditorReview
- RiskRegister
- RemediationTask

Assessment states:
- draft
- in_progress
- pending_ai
- self_assessed
- ready_for_auditor
- auditor_review
- approved
- failed
- closed

Each AssessmentControlResult must store:
- control
- applicability
- system_status
- ai_suggested_status
- auditor_final_status
- final_status
- score_weight
- risk_level
- observation
- remediation_summary

Acceptance criteria:
- Company can have multiple assessments.
- Each assessment has independent control results.
- Scores are calculated from AssessmentControlResult, not from AI directly.
- Historical assessments are preserved.
- Tests verify lifecycle transitions.
