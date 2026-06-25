# CyberTrust KSA — Docker Deployment Runbook
> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. The internal Django project package name remains `cybertrust_ksa` (former internal project name: CyberTrust KSA); it is technical-only and intentionally unchanged.


**Status:** Ready for UAT (deployment packaging). This runbook documents how to build and
operate the CyberTrust stack with Docker. It is **not** a production go-live; HTTPS,
secrets, and backups must be configured per the security checklist below.

> Compose command: examples below use `docker compose` (Compose v2). If you have the
> standalone binary, substitute `docker-compose` (v1). Both work with this `docker-compose.yml`.

## Prerequisites
- Docker Engine + Docker Compose (v2 plugin `docker compose`, or standalone `docker-compose`).
- A populated `.env` at the repo root (see env vars below). **Never commit `.env`.**
- Outbound network access for the image build (pip/base image).

## File overview
| File | Purpose |
|---|---|
| `Dockerfile` | Django + Gunicorn image (python:3.12-slim, non-root). |
| `docker-compose.yml` | `web` (Gunicorn) + `db` (PostgreSQL 16) + named volumes. |
| `.dockerignore` | Keeps `.env`, `db.sqlite3`, `media/`, `.venv/`, `.git/` out of the build context. |
| `deployment/docker/entrypoint.sh` | Waits for DB → `migrate` → `collectstatic` → exec Gunicorn. |
| `deployment/docker/env.example` | Placeholder env file (copy to `.env`). |

## Required environment variables
Copy the example and edit values:
```bash
cp deployment/docker/env.example .env
```
Key variables (full list in `deployment/docker/env.example`):
- `DJANGO_SECRET_KEY` — long random secret (required).
- `DEBUG=False` — production.
- `ALLOWED_HOSTS` — comma-separated hostnames.
- `CSRF_TRUSTED_ORIGINS` — comma-separated `https://host` origins.
- `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` — setting `POSTGRES_DB` switches the app to PostgreSQL.
- `WEB_PORT` — host port (default 8000).
- `OPENAI_API_KEY` — optional; advisory AI only.

> The app defaults to SQLite when `POSTGRES_DB` is **not** set (local/dev). The Docker
> stack sets `POSTGRES_DB`, so it uses PostgreSQL automatically.

## First-time setup
```bash
cp deployment/docker/env.example .env      # then edit secrets
docker compose build
docker compose up -d                       # entrypoint runs migrate + collectstatic
docker compose ps                          # confirm db healthy, web healthy
```

## Common operations
- **Build:** `docker compose build`
- **Start:** `docker compose up -d`
- **Migrate** (also run automatically on start): `docker compose exec web python manage.py migrate`
- **Collect static** (also run automatically on start): `docker compose exec web python manage.py collectstatic --noinput`
- **Create superuser** (manual, intentional): `docker compose exec web python manage.py createsuperuser`
- **Seed official controls** (as needed): `docker compose exec web python manage.py seed_framework_versions` then the official import commands (see ADMIN_GUIDE.md).
- **Logs:** `docker compose logs -f web` · `docker compose logs -f db`
- **Restart:** `docker compose restart web`
- **Stop:** `docker compose down` (add `-v` only if you intend to delete volumes/data).

## Backup (PostgreSQL)
```bash
# Logical dump to the host
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%F).sql
# Media files (uploaded evidence) live in the media_volume:
docker run --rm -v "$(basename "$PWD")_media_volume":/m -v "$PWD":/out alpine \
  tar czf /out/media_backup_$(date +%F).tgz -C /m .
```

## Restore (outline)
```bash
# Restore DB into a running, empty db service
cat backup_YYYY-MM-DD.sql | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
# Restore media into the media_volume
docker run --rm -v "$(basename "$PWD")_media_volume":/m -v "$PWD":/in alpine \
  sh -c "cd /m && tar xzf /in/media_backup_YYYY-MM-DD.tgz"
```
See `DOCKER_ROLLBACK.md` for image/release rollback.

## Healthcheck verification
- Endpoint: `GET /healthz/` → `{"status": "ok"}` (public, no sensitive data).
- The `web` service healthcheck calls it internally; `docker compose ps` shows `healthy`.
- Manual: `curl -fsS http://localhost:${WEB_PORT:-8000}/healthz/`

## Smoke test checklist (post-deploy)
1. `GET /healthz/` returns `{"status":"ok"}`.
2. Login works; landing/dashboard render.
3. Intake → framework approval → control plan → evidence checklist.
4. Evidence Upload v2 accepts a valid file; rejects a disallowed extension.
5. Advisory analysis runs (staff) and stays advisory.
6. Auditor sets a ControlAssessment; reports/gap analysis reflect it.
7. Static assets load (collectstatic succeeded).

## Security checklist (must be satisfied before exposing publicly)
- [ ] `DEBUG=False`.
- [ ] `ALLOWED_HOSTS` set to real hostnames.
- [ ] `CSRF_TRUSTED_ORIGINS` set to the HTTPS origins.
- [ ] Secure cookies (`SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE`) — enabled automatically when `DEBUG=False`.
- [ ] HTTPS terminated at a reverse proxy; `SECURE_PROXY_SSL_HEADER` honored (already configured in settings when `DEBUG=False`).
- [ ] Secrets only in `.env` (git-ignored); never in the image or VCS.
- [ ] `static_volume` / `media_volume` persisted and backed up.
- [ ] Backup schedule defined and a restore tested.
