# CyberTrust KSA — Docker UAT / Smoke Test Report

**Status:** Ready for internal UAT (Docker runtime validated). **Not** production go-live
(HTTPS/domain/backups/monitoring/secrets must still be provisioned on a real server).

## Environment used
- Host: Linux; Docker Engine **29.1.3**; Compose **docker-compose 1.29.2** (standalone).
- Image: `1saudicyber_web` (python:3.12-slim, Gunicorn 26, non-root).
- Database: `postgres:16-alpine` (service `db`).
- App settings: `DEBUG=True` for the route smoke (HTTP), PostgreSQL via `POSTGRES_DB`.
- **Secret safety:** the developer's real `.env` was moved out of the repo for the duration of
  the run and restored afterward. A git-ignored UAT env (`deployment/docker/uat.env`,
  placeholders only, `OPENAI_API_KEY` empty) was used. No real secret was used or printed.

## Commands run (high level)
```
# Local (host venv)
python manage.py makemigrations --check --dry-run   # No changes detected
python manage.py check                              # no issues
python manage.py test                               # 452 OK

# Docker runtime (standalone docker-compose)
docker-compose config        # valid (no real secrets — UAT env)
docker-compose build web     # Successfully built
docker-compose up -d         # db + web created
docker-compose ps            # db healthy, web healthy
docker-compose logs web      # migrate + collectstatic + gunicorn, no errors
docker-compose exec web python manage.py check         # no issues
docker-compose exec web python manage.py migrate --check  # exit 0 (no pending)
curl -f http://localhost:8000/healthz/                 # {"status":"ok"} HTTP 200
docker-compose exec web python manage.py shell  < route/security smoke (27/27)
docker-compose exec web python manage.py test          # full suite on PostgreSQL
docker-compose down -v       # tear down (containers + ephemeral volumes)
```

## Services started
- `db` (postgres:16-alpine) → **Up (healthy)** via `pg_isready`.
- `web` (gunicorn) → **Up (healthy)** via `/healthz/` probe (3 workers booted, no errors).

## Healthcheck results
- Internal container healthcheck: **healthy** on first poll.
- Host probe `GET http://localhost:8000/healthz/` → `{"status": "ok"}`, **HTTP 200**.
- Production note: `/healthz/` is exempted from the HTTPS redirect (`SECURE_REDIRECT_EXEMPT`)
  so the probe still returns 200 over HTTP behind a TLS-terminating proxy when `DEBUG=False`.

## Startup / migrations
- Entrypoint applied **all migrations** cleanly on PostgreSQL (auth, core, compliance 0001–0011,
  auditor_portal, monitoring, sessions, admin).
- `collectstatic`: **157 static files copied, 453 post-processed** (WhiteNoise manifest).
- `migrate --check` inside the container: **exit 0** (no pending migrations).

## Pages / routes tested (live container, Django test client, host `localhost`)
Anonymous (must redirect to login → **302**): dashboard, intake, framework review,
control plan, evidence checklist, auditor review, reports index, executive summary,
gap analysis, evidence matrix. Public: `/healthz/` (200), `/login/` (200).
Authenticated staff (must render → **200**): all of the above pages plus evidence-matrix
**CSV** and **XLSX** exports.
**Result: 27/27 route + security checks passed.**

## Workflow smoke scenarios
- **Scenario A (Auth/Journey):** login (force_login) works; dashboard + all journey pages
  render 200 with empty-state guidance; no data from other companies present.
- **Scenario B (Compliance workflow):** the full create-path (intake → framework approval →
  control plan → evidence checklist → Evidence Upload v2 → advisory analysis → auditor
  assessment → reports/exports) is exercised comprehensively by the **full test suite run
  inside the container against PostgreSQL** (see Test results). Advisory analysis without a real
  AI key falls back safely (no compliance decision). A data-complete manual business UAT with the
  full 417-control official library re-seeded in Postgres was **not** performed in this smoke;
  it is covered by the suite and can be done on the UAT server (see Limitations).
- **Scenario C (Security quick checks):** anonymous users are redirected from protected pages;
  a non-staff user cannot generate assessments or the evidence checklist (no rows created);
  reports never count unreviewed controls as compliant (0% on an empty company).

## Test results
- **Local (SQLite):** `python manage.py test` → **452 OK**.
- **In-container (PostgreSQL):** `docker-compose exec web python manage.py test` →
  **Ran 452 tests — OK** (the same suite executed against PostgreSQL inside the container).

## Rollback / teardown
- Tear down: `docker-compose down` (add `-v` to also remove the ephemeral UAT volumes).
- Image/release rollback procedure: see `DOCKER_ROLLBACK.md`.

## Secret safety notes
- No `.env`, `db.sqlite3`, secrets, volumes, media, or container logs containing secrets were
  committed. The real developer `.env` was never used by the UAT run and was restored intact.
- **Recommendation:** if the developer `.env`'s `OPENAI_API_KEY` was ever exposed in shell
  output/logs, rotate it. Keep `.env` strictly local and git-ignored.

## Official control library
- **Not loaded** into the Docker UAT database (the smoke ran on an empty schema). Route and
  security smoke do not require it. Full business UAT with the official 417-control library
  should be performed on the UAT server using the seed/import commands in `ADMIN_GUIDE.md`.

## Limitations
- Route smoke ran with `DEBUG=True` so pages are reachable over plain HTTP; production uses
  `DEBUG=False` behind TLS (only `/healthz/` is HTTP-exempt).
- Compose v2 plugin (`docker compose`) is absent on this host; standalone `docker-compose` 1.29.2 used.
- No real server, domain, HTTPS, backups, or monitoring were configured (out of scope).
