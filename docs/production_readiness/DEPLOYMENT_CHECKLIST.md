# CyberTrust KSA — Deployment Readiness Checklist
> **Branding note:** Public brand and domain: **1SaudiCyber — cyber-5.com**. The internal Django project package name remains `cybertrust_ksa` (former internal project name: CyberTrust KSA); it is technical-only and intentionally unchanged.


**Status:** Needs configuration. This is a **documentation-only** checklist — no Docker or
deployment tooling is implemented in Phase 3K.

> **Docker deployment is the next phase: Phase 3L — Docker Deployment Management.**

Legend: ☐ to do · ⚙ needs configuration · ✅ done in app layer

## Environment variables
- ⚙ `SECRET_KEY` — set from a secrets store, never committed.
- ⚙ `DEBUG=False` in production.
- ⚙ `ALLOWED_HOSTS` — real hostnames.
- ⚙ Database and API credentials via environment, not source.
- ✅ `.env` is git-ignored.

## Database decision
- ☐ Choose production DB (PostgreSQL recommended) and configure `DATABASES`.
- ⚙ `db.sqlite3` is dev-only and git-ignored; do not ship it.

## Static files
- ⚙ `collectstatic` to a served `STATIC_ROOT`; WhiteNoise is present for static serving.

## Media files
- ⚙ Configure `MEDIA_ROOT` / object storage for uploaded evidence; ensure backups and access control.

## Migrations
- ✅ No pending migrations (`makemigrations --check --dry-run` → clean).
- ⚙ Run `migrate` on deploy.

## Superuser / admin
- ⚙ Create the initial superuser; provision staff/auditor accounts.

## Allowed hosts
- ⚙ Set `ALLOWED_HOSTS` to the deployment domains.

## CSRF trusted origins
- ⚙ Set `CSRF_TRUSTED_ORIGINS` for the HTTPS origin(s).

## Secure cookies
- ⚙ `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, secure/HttpOnly flags.

## HTTPS / reverse proxy
- ⚙ Terminate TLS at a reverse proxy; set `SECURE_PROXY_SSL_HEADER`, HSTS, redirects.

## Logging
- ⚙ Configure structured logging and error reporting (no secrets in logs).

## Backup / restore
- ☐ Define DB + media backup schedule and a tested restore procedure.

## OpenAI / API keys (if advisory AI is enabled)
- ⚙ Provide provider API keys via environment; analysis remains advisory only.
- Note: advisory analysis is optional; the workflow functions without it.

## File upload storage
- ⚙ Confirm evidence storage backend, size limits, and retention.

## Health check
- ☐ Expose/confirm a health endpoint for the load balancer.

## Rollback plan
- ☐ Document image/release rollback and DB migration rollback strategy (finalized in Phase 3L).

## Smoke test (post-deploy)
- ☐ Login → intake → framework approval → control plan → checklist → upload → analysis → assessment → reports.
