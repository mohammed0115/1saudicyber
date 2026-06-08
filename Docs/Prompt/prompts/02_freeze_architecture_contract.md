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
