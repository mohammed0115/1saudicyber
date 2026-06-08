# 00_ALL_PROMPTS_MASTER

هذه نسخة مجمعة من كل برومبتات الإصلاح بالترتيب.


---

# Prompt 01 — Repository Audit & Current-State Report

You are working on an existing Django project for CyberTrust KSA.

Do NOT rewrite the project from scratch.
Do NOT delete working functionality.
Your task is to perform a careful current-state audit only.

Reference requirements:
- CyberTrust KSA SRS v1.0
- CyberTrust KSA Developer Prototype v3.2
- Third Party Cybersecurity Compliance Report Template for Aramco/SACS-002

Inspect the current Django project and produce CURRENT_SYSTEM_AUDIT.md.

The report must include:
1. Current Django apps and their responsibilities.
2. Existing models, views, URLs, templates, services, Celery tasks, and APIs.
3. Which SRS requirements are already implemented.
4. Which SRS requirements are missing.
5. Which v3.2 scenarios are already supported.
6. Which v3.2 scenarios are missing or only mocked.
7. Existing control framework support: NCA, Aramco, SABIC.
8. Evidence upload/OCR/AI analysis status.
9. Auditor portal status.
10. Monitoring/alerts status.
11. Security gaps: RBAC, tenant isolation, audit logs, file security.
12. Broken URLs, broken imports, model mismatch, migration issues.
13. Risk rating for each gap: Critical / High / Medium / Low.
14. Recommended refactor order.

Run:
- python manage.py check
- python manage.py makemigrations --check
- python manage.py migrate
- pytest if available

If tests cannot run, explain why.

Deliverables:
- CURRENT_SYSTEM_AUDIT.md
- COMMANDS_RUN.md
- BUGS_FOUND.md

Acceptance criteria:
- No code changes except documentation.
- The report must be honest and specific.



---

# Prompt 02 — Freeze Architecture Contract

You are refactoring the existing Django project toward the official CyberTrust KSA architecture.

Do NOT rebuild from scratch.
Preserve existing apps where reasonable.
Create an architecture contract that every future implementation must follow.

Target architecture:
1. Core: users, companies, registration, RBAC, tenant isolation.
2. Compliance: frameworks, domains, controls, mappings, assessments.
3. Evidence: uploads, OCR, extracted text, file metadata.
4. AI Engine: OpenAI classification and evidence analysis only.
5. Rule Engine: final machine decision C/PC/NC/N/A or Compliance/Noncompliance.
6. Risk Engine: likelihood, impact, risk score, heatmap.
7. Remediation: roadmap, tasks, owners, dates.
8. Auditor Portal: auditor review, override, findings, sign-off.
9. Dashboard: executive, compliance, IT/security, business unit views.
10. Monitoring: scores, alerts, continuous monitoring, control testing.
11. Reports: NCA report, Aramco/SACS report, SABIC report, executive exports.
12. Audit Trail: every sensitive action logged.

Create:
- ARCHITECTURE_DECISION_RECORD.md
- TARGET_MODULE_MAP.md
- DATA_FLOW.md
- RULES_FIRST_AI_SECOND_AUDITOR_FINAL.md

Important principle:
AI must never be the final authority.
AI produces suggestions.
Rule Engine produces system verdict.
Auditor produces final verdict.

Acceptance criteria:
- Architecture documents created.
- Existing project structure mapped to target structure.
- No destructive code changes.



---

# Prompt 03 — Multi-Framework Control Library Repair

Implement or repair the multi-framework Control Library.

The platform must support:
1. NCA ECC controls.
2. Saudi Aramco SACS-002 controls.
3. SABIC CyberTrust controls.
4. Cross-framework mappings.

The SRS states the platform manages 334 controls across NCA, Aramco, and SABIC.
The Third Party Cybersecurity Compliance Report Template contains Aramco/SACS-002 controls using references like TPC-1, TPC-2, etc.

Do not hardcode controls in templates.
Store controls in the database.

Required models or equivalent:
- Framework
- FrameworkVersion
- Domain
- Control
- ControlClause
- EvidenceRequirement
- ControlMapping
- ControlApplicabilityRule

Each Control must support:
- framework
- code/reference
- title_en
- title_ar
- description_en
- description_ar
- domain
- priority
- mandatory flag
- evidence types
- evidence guidance en/ar
- applicable sectors
- applicable company sizes
- applicable third-party classifications
- active/version fields

Add management commands:
- import_controls_from_excel
- export_controls_to_excel
- seed_minimum_frameworks

Acceptance criteria:
- NCA, Aramco, SABIC frameworks exist.
- Controls can be filtered by framework/domain/priority.
- Aramco TPC controls support Compliance/Noncompliance output.
- NCA controls support C/PC/NC/N/A output.
- Tests verify framework creation, control import, and filtering.



---

# Prompt 04 — Company Registration & Organization Profile Repair

Repair company registration and organization profiling according to SRS FR-002.

The registration must be standalone.
Do NOT integrate Nafath.
Do NOT integrate Wathiq.
Do NOT call external government verification APIs.

Registration must collect:
- company name Arabic
- company name English
- Commercial Registration number
- sector
- company size
- vendor/certification targets:
  - Saudi Aramco SACS-002
  - SABIC CyberTrust
  - Government NCA ECC
- primary contact information
- user email/password

Validation:
- CR number must be 10 digits.
- Duplicate CR number must be prevented.
- Email verification must be supported.
- Company profile changes must trigger re-classification.

Add or repair:
- Company model
- CompanyProfile fields
- CompanyTargetFramework
- ContactPerson fields
- Registration form/API
- Tests

Acceptance criteria:
- User can register a company without external APIs.
- Company has sector, size, and target frameworks.
- Duplicate CR is rejected.
- Email verification flow works or is safely stubbed in development.



---

# Prompt 05 — Smart Classification Engine Repair

Repair the Smart Classification Engine according to SRS FR-003 and Prototype v3.2 Phase 1.

Important:
Use deterministic rules first.
Use AI only for explanation and bilingual classification summary.

Classification must determine:
1. Applicable frameworks:
   - Aramco target → SACS-002
   - SABIC target → SABIC CyberTrust
   - Government target → NCA ECC
2. Risk tier:
   - Tier 1 Critical: Oil & Gas, Government, Banking with Large/Enterprise size
   - Tier 2 High: Healthcare, Telecom, Energy with Medium+
   - Tier 3 Standard: all others
3. Required control count.
4. Priority domains.
5. Estimated timeline.
6. Bilingual explanation.

Add:
- ClassificationResult model
- ClassificationHistory model
- classify_company_service
- admin override fields
- reclassification trigger when company profile changes

AI requirements:
- Output JSON only.
- Temperature 0.1.
- Store prompt, response, model, confidence, and timestamp.
- Gracefully handle OpenAI failure by using deterministic fallback.

Acceptance criteria:
- Classification works without OpenAI.
- OpenAI adds explanation only.
- Classification history is stored.
- Admin can override classification.
- Tests cover all sector/size/target combinations.



---

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



---

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



---

# Prompt 08 — Evidence Upload, OCR & File Security Repair

Repair evidence upload and OCR according to SRS FR-005.

Supported files:
- PDF
- PNG/JPG/JPEG/TIFF
- DOCX
- XLSX
- TXT

Constraints:
- Max file size 50 MB.
- Store original file.
- Extract text.
- Store extracted text.
- Track uploader, upload date, file metadata.
- Allow multiple evidence files per control.
- Allow deletion with audit trail.

OCR:
- Use Tesseract.
- Support Arabic and English.
- For PDFs use pdf2image + OCR.
- For DOCX/XLSX extract text directly where possible.
- If OCR fails, allow manual text entry.

Security:
- Validate file extension and MIME type.
- Prevent path traversal.
- Store files per company/assessment securely.
- Add optional virus scanning hook.
- Do not expose raw storage paths in templates/API.

Create/repair:
- Evidence model
- EvidenceTextExtractionResult
- OCR service
- upload API/view
- upload UI
- audit log events

Acceptance criteria:
- Upload works for all supported file types.
- OCR extraction stored.
- Arabic/English text extraction supported or failure handled gracefully.
- Invalid files are rejected.
- Audit trail records upload/delete.
- Tests cover file validation and OCR fallback.



---

# Prompt 09 — AI Evidence Analyzer Repair

Repair AI Evidence Analyzer according to SRS FR-006.

Important:
AI does not issue final verdict.
AI produces an evidence analysis suggestion only.

Input:
- control requirements
- evidence requirements
- extracted text
- company context
- framework
- previous analysis if re-analysis

AI must return JSON:
{
  "suggested_status": "compliant|partially_compliant|non_compliant|insufficient_evidence",
  "confidence": 0-100,
  "reasoning_en": "...",
  "reasoning_ar": "...",
  "recommendations_en": "...",
  "recommendations_ar": "...",
  "missing_elements": [],
  "evidence_strength": "strong|medium|weak",
  "needs_human_review": true/false,
  "fabrication_or_template_risk": "low|medium|high"
}

Evaluation criteria:
- relevance
- completeness
- currency
- specificity
- implementation evidence
- not only generic policy wording

Operational requirements:
- Retry 3 times with exponential backoff.
- Timeout after 60 seconds.
- Rate limit API calls.
- Store raw request/response safely.
- Mask sensitive secrets from prompts.
- Batch analysis must be queued with Celery.

Acceptance criteria:
- AI result is stored separately from final status.
- Low confidence flags human review.
- OpenAI failure does not break user workflow.
- Tests use mocked AI responses.



---

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



---

# Prompt 11 — Risk, Gap Analysis & Remediation Repair

Repair Gap Analysis, Risk Engine, and Remediation Roadmap according to SRS FR-007.

The system must:
1. Calculate compliance score per framework.
2. Calculate score per domain.
3. Identify non-compliant and partially compliant controls.
4. Prioritize gaps by:
   - control criticality
   - mandatory flag
   - remediation effort
   - audit probability
5. Generate risk score 0-100.
6. Estimate audit failure probability.
7. Generate remediation roadmap.
8. Track gap closure.

Create:
- Gap
- RiskRegister
- RemediationTask
- RiskScoringService
- RemediationRoadmapService

Risk fields:
- likelihood 1-5
- impact 1-5
- score
- level: High/Medium/Low
- treatment: Mitigate/Accept/Transfer/Avoid
- owner
- target date

Roadmap buckets:
- Immediate: 0-30 days
- Short-Term: 31-90 days
- Medium-Term: 91-180 days
- Long-Term: 181+ days

Acceptance criteria:
- Gaps are generated from AssessmentControlResult.
- Risk register is created automatically.
- Remediation tasks have owner/status/date.
- Dashboard can display gap and risk summary.
- Tests cover score and roadmap generation.



---

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



---

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



---

# Prompt 14 — Role-Specific Dashboards Repair

Repair role-specific dashboards according to SRS FR-008 and Prototype v3.2 Phase 6.

Roles:
- Executive
- Compliance Officer
- IT/Security Team
- Business Unit Manager
- Company Admin
- Platform Admin
- Auditor

Dashboard rules:
- Data must be scoped by company and role.
- No user can see another company's data.
- Executive dashboard is read-only.
- Compliance dashboard shows full control checklist.
- IT/Security dashboard focuses on technical controls, vulnerabilities, automated tests, drift alerts.
- Business Unit dashboard shows department tasks, training, policy acknowledgments.
- Auditor dashboard uses auditor assignments only.

Create endpoints/views:
- /dashboard/executive/
- /dashboard/compliance/
- /dashboard/it-security/
- /dashboard/business-unit/
- /auditor/

API endpoints:
- /api/v1/dashboard/executive/
- /api/v1/dashboard/compliance/
- /api/v1/dashboard/it-security/
- /api/v1/dashboard/business-unit/

Acceptance criteria:
- Each role lands on correct dashboard.
- RBAC enforced.
- Dashboard metrics come from assessment/risk/remediation data.
- Tests verify role access.



---

# Prompt 15 — Monitoring, Alerts & Continuous Compliance Repair

Repair Continuous Monitoring according to SRS FR-010 and Prototype v3.2 Phase 10.

Start with realistic MVP monitoring.
Do not fake 200 live integrations.
Build extensible architecture first.

Monitoring must support:
- Daily compliance score recalculation.
- Monthly auto-generated reports.
- Certificate renewal countdown.
- Evidence expiration alerts.
- Policy review due alerts.
- Compliance score drop alerts.
- New framework/control version alerts.
- Dashboard notification center.
- Email notifications for critical alerts.

Create:
- ComplianceScoreSnapshot
- Alert
- AlertRule
- NotificationLog
- MonitoringRun
- scheduled Celery tasks

Alert severity:
- Critical
- High
- Medium
- Low
- Info

Acceptance criteria:
- Daily score recalculation task works.
- Alert generated when score drops below threshold.
- Evidence expiration alert works.
- Email notification is logged.
- Monitoring dashboard shows active alerts.
- Tests cover scheduled checks.



---

# Prompt 16 — Integrations Hub & Automated Control Testing Foundation

Build the foundation for Integrations Hub and Automated Control Testing from Prototype v3.2.

Important:
Implement architecture and mock/test connectors first.
Do not claim real 200+ integrations are working unless implemented.

Create:
- IntegrationProvider
- IntegrationConnection
- IntegrationCredential
- ControlTestDefinition
- ControlTestRun
- ControlTestResult
- ConnectorEvent

Providers catalog can include:
- Azure AD
- AWS
- Microsoft 365
- Qualys
- CrowdStrike
- Fortinet
- Palo Alto
- SIEM generic
- Manual Upload

Credential security:
- Encrypt tokens/API keys.
- Never log secrets.
- Allow connection test.
- Allow disable/revoke.

Automated control testing:
- Test frequency: 15 minutes to 24 hours.
- Each test maps to one or more controls.
- Results: pass/fail/warning/error.
- Evidence link generated from test result.
- Failed tests create alerts and update control status through Rule Engine.

Acceptance criteria:
- Integration catalog visible.
- User can create mock integration connection.
- Automated test run can be simulated.
- Test result maps to control.
- Failed test creates alert.
- Tests cover connector lifecycle.



---

# Prompt 17 — Security, Tenancy & Audit Trail Hardening

Perform security hardening across the existing Django project.

Requirements from SRS:
- RBAC with least privilege.
- Full audit trail.
- File upload security.
- CSRF protection.
- Input validation.
- API rate limiting.
- Data sovereignty configuration.
- Secure session management.
- MFA support or MVP-ready structure.
- Audit logging for all user actions.

Implement:
- Tenant isolation checks for every company-scoped query.
- Permission decorators/mixins.
- Object-level permission tests.
- AuditLog model and service.
- Security middleware/config review.
- File access authorization.
- Rate limits for AI and upload endpoints.
- Safe error handling.

Audit events:
- login/logout
- registration
- company update
- classification
- control status change
- evidence upload/delete
- AI analysis
- auditor override
- report generation
- alert creation
- integration credential changes

Acceptance criteria:
- No cross-company data leakage.
- Unauthorized users get 403.
- Every sensitive action creates audit log.
- File URLs cannot be guessed or accessed directly.
- Security tests included.



---

# Prompt 18 — API Contract, Tests & Final Repair Gate

Create or repair API contracts and final test gate.

Required API endpoints from SRS:
- POST /api/v1/register/
- POST /api/v1/login/
- POST /api/v1/classify/
- GET /api/v1/controls/
- GET /api/v1/controls/{id}/
- POST /api/v1/evidence/upload/
- POST /api/v1/evidence/{id}/analyze/
- GET /api/v1/gap-analysis/
- GET /api/v1/dashboard/executive/
- GET /api/v1/dashboard/compliance/
- GET /api/v1/monitoring/scores/
- GET /api/v1/monitoring/alerts/
- POST /api/v1/reports/generate/
- GET /api/v1/auditor/assignments/
- POST /api/v1/auditor/review/{id}/

Add:
- OpenAPI/Swagger documentation.
- API serializers.
- Standard error response format.
- Authentication/authorization checks.
- Pagination/filtering for controls/evidence/alerts.
- Tests for all endpoints.

Final E2E flows:
1. Register company.
2. Classify company.
3. Generate applicable controls.
4. Upload evidence.
5. OCR/extract text.
6. AI analysis.
7. Rule Engine status.
8. Gap analysis.
9. Auditor review and override.
10. Generate NCA report.
11. Generate Aramco/SACS report.
12. Monitoring alert generated.

Acceptance criteria:
- python manage.py check passes.
- migrations pass.
- test suite passes.
- E2E scenario documented with screenshots or logs.
- FINAL_REPAIR_REPORT.md generated.

