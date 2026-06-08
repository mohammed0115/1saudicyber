# Prompt 06 — Applicability Engine Repair

Build the Applicability Engine.

Purpose:
Determine which controls apply to a company before evidence upload.

Inputs:
- company sector
- company size
- target frameworks
- third-party classification
- cloud usage
- network connectivity
- critical data processing
- outsourced infrastructure
- customized software
- government/NCA target
- SABIC/Aramco target

For Aramco/SACS-002:
Use Third Party classifications:
- General Requirements apply to all third parties.
- Specific Requirements depend on classification:
  - Outsourced Infrastructure
  - Customized Software
  - Network Connectivity
  - Critical Data Processor
  - Cloud Computing Service

For NCA:
Support N/A where controls do not apply, with justification.

Create:
- AssessmentScope
- ApplicabilityResult
- ApplicabilityJustification
- apply_controls_to_company_service

Rules:
- Applicable controls become part of assessment.
- Non-applicable controls require justification.
- AI can suggest justification text, but system rule decides applicability.

Acceptance criteria:
- Assessment scope is generated after classification.
- Applicable controls are assigned to the company.
- N/A controls are stored with justification.
- Aramco general controls apply to all Aramco third parties.
- Aramco specific controls apply based on third-party classification.
- Tests verify correct applicability.
