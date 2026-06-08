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
