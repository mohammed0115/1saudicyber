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
