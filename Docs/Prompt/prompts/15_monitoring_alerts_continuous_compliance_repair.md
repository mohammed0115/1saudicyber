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
