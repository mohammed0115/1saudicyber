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
