# CyberTrust KSA — Implementation of Missing / Incomplete Items

This bundle is the FULL updated Django project with the open implementation gaps built out.
The conceptual gaps from Manus (G-C01..C09, C11: data-verification policy, AI-Copilot scope,
UX, legal, NLP training, change management) are product/process decisions, not code — they remain
in the register as guidance.

## What was implemented (and verified: `manage.py check` clean, 17 tests passing)

| Gap | Item | What was added |
|-----|------|----------------|
| G-I02 | REST API `/api/v1` | New `api` app: DRF serializers + views for register, controls, classify, evidence upload/analyze, gap-analysis, dashboards, monitoring, auditor. JWT auth (SimpleJWT) satisfies NFR-013. |
| G-I03 | Async + scheduler | `cybertrust_ksa/celery.py`, `monitoring/tasks.py` (recalc, monthly reports, checks, async evidence), beat schedule. Evidence OCR+AI refactored into `compliance/services.process_evidence_pipeline` (async via Celery, sync fallback). Sync command `run_monitoring`. |
| G-I04 | Real-time feed | SSE endpoint `monitoring/api/stream/` (works under WSGI/Gunicorn). True WebSocket can later replace it with Channels. |
| G-I05 | Email | EMAIL backend config; `core/services.send_verification_email` + `send_alert_email`; email verification on register; Django password-reset views/templates. |
| G-I06 | MFA | TOTP (pyotp): `mfa_setup` enrollment, `mfa_challenge` at login, User.mfa_enabled/secret. |
| G-I07 | Reporting | `dashboard/reports.py`: gap-analysis PDF + controls Excel export (download URLs); certificate issuance on a passing audit. |
| G-I09 | Evidence types | DOCX (python-docx) + XLSX (openpyxl) + TXT extraction added to the OCR pipeline. |
| G-I12 | Tests | `core/tests.py` — 17 tests across forms, email, MFA, extraction, monitoring, reporting, API, audit log, PDPL. |
| G-I13 | Security hardening | `core/middleware.py` (CSP + audit log); DRF throttling (100/min); SECURE_* settings gated on DEBUG; LocaleMiddleware enabled. |
| G-I14 | PDPL | Retention settings + `purge_expired_data` command; right-to-deletion endpoint `/account/delete/`. |

## How to run
```
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_all_controls        # loads all 334 controls (already seeded in the bundled db)
python manage.py test                     # 17 tests
python manage.py runserver
# Optional background jobs (need Redis):
celery -A cybertrust_ksa worker -l info
celery -A cybertrust_ksa beat -l info
# Or run monitoring synchronously (no Redis):
python manage.py run_monitoring --monthly
```

## Needs external infrastructure to fully activate (code is ready)
- Celery beat/worker need a running Redis broker.
- Real email delivery needs SMTP env vars (defaults to console backend in dev).
- OpenAI features need OPENAI_API_KEY.
- SSE works as-is; a true WebSocket feed would add Django Channels + Daphne.
