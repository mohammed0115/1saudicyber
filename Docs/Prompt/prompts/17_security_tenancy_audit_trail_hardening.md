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
