# Prompt 13 — Report Generator Repair: NCA + Aramco/SACS

Repair Report Generator.

The system must generate at least two report types:

1. NCA ECC Assessment Report
Uses:
- C / PC / NC / N/A
- Executive summary
- methodology
- detailed controls
- evidence/observations
- risk level
- remediation actions
- gap analysis
- risk register
- remediation roadmap
- sign-off

2. Aramco/SACS-002 Third Party Compliance Report
Based on Third Party Cybersecurity Compliance Report Template.
Must include:
- Third Party Information
- Vendor ID
- Business address
- Third Party Classification
- Contact person
- Audit Firm Information
- Assessors
- Approved by
- Guidelines
- Assessment Controls
- General Requirements
- Specific Requirements
- Report Summary
- Compliance / Noncompliance counts and percentages

Reports must:
- Be generated from database results, not static text.
- Support Arabic and English where applicable.
- Support PDF export.
- Support Excel export for control matrix.
- Include version, generated date, and assessment ID.

Acceptance criteria:
- NCA report generated from assessment.
- Aramco/SACS report generated from assessment.
- Counts and percentages are correct.
- Reports do not expose internal AI prompts.
- Tests verify report calculations.
