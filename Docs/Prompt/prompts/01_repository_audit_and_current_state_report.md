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
