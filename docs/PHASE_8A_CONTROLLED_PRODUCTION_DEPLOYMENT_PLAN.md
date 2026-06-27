# Phase 8A — Controlled Production Deployment Plan

> **Branding note:** Public brand and domain: **1SaudiCyber — 1saudicyber.com**. Internal package
> `cybertrust_ksa` (technical-only).

**Status:** PLANNING ONLY. No deployment, no SSH, no production change was performed in this phase.
Execution requires explicit owner approval and is a separate phase (8B).

## 0. Targets & facts (verified locally)
| Item | Value |
|---|---|
| Local repo | `/home/mohamed/1saudicyber` |
| Production path | `/opt/1saudicyber` |
| Domain / IP | `https://1saudicyber.com` / `88.222.220.132` |
| Branch | `cybertrust-execution` |
| **Target commit (deploy this)** | **`5771735`** (Phase 7C) |
| Local baseline | `check` clean · `makemigrations --check` clean · full suite green (see report) |
| Compose services (verified in `docker-compose.yml`) | `web` (build .), `db` (postgres:16-alpine) |
| Named volumes | `postgres_data`, `static_volume`, `media_volume` |
| Health endpoint | `GET /healthz/` → `{"status":"ok"}` (public) |
| Official control total | **417** (legacy 334 must never show as current total) |

## 1. Local baseline (must be green before deploy)
```bash
cd /home/mohamed/1saudicyber
python manage.py check                       # → no issues
python manage.py makemigrations --check --dry-run   # → No changes detected
python manage.py test                        # → full suite passes
```
If local tests fail → **NO-GO** until green.

## 2. Production gap (MUST be verified on the server before execution)
Production was last deployed around **`b2a411c` (UX-WIZARD-A)**. Local commits believed ahead of prod:
```
86bfbf8 UX-1B-RTL-FIX-A      5799b9d UX-1B-CLEANUP-A     4ae4582 UX-1C i18n
10316aa 6A Classification    40aae93 6B Applicability    55a59c0 6C Extraction
cc0fe00 6C-FIX-A             cb0c3c8 6D AI Advisory       76cbad9 6E Rule Engine
794fe0f 6F Auditor Verdict   a79bd38 7A UAT Gate          3ee67aa 7B Reports
5771735 7C Pre-Deploy (TARGET)
```
> **Do not assume** production is exactly at `b2a411c`. First action on the server is to record the real
> current commit (`git rev-parse HEAD`, `git log --oneline -10`, `git status --short`) — this becomes the
> **rollback commit**. If the working tree is dirty, **NO-GO** until reconciled.

## 3. Migration inventory
Additive migrations likely not yet applied on prod (all **CreateModel**, no destructive ops):
```
compliance/0012_evidencetextextraction
compliance/0013_evidenceaianalysis
compliance/0014_evidenceruleevaluation
compliance/0015_auditorfinalverdict
```
Plus earlier app migrations from phases 4x–5B if the live server predates them
(`risk/0001`, `monitoring/0002`, `billing`, `auditors`, `core/0004`). **Verify before migrate** (do NOT run on prod in this phase):
```bash
# future, on server only
docker compose run --rm web python manage.py showmigrations compliance monitoring risk core auditors billing
```
**Risk:** additive only → low schema risk, but a **DB backup is still mandatory** before `migrate`.

## 4. Environment / secret checklist (verify on host — never print values)
From `deployment/docker/env.example`, confirm `/opt/1saudicyber/.env` has, with correct values:
`DJANGO_SECRET_KEY` · `DEBUG=False` · `ALLOWED_HOSTS` (incl. `1saudicyber.com`) ·
`CSRF_TRUSTED_ORIGINS` (`https://1saudicyber.com`) · `DJANGO_SETTINGS_MODULE` ·
`POSTGRES_DB/USER/PASSWORD/HOST/PORT` · `WEB_PORT` (bound to `127.0.0.1:8000` behind Nginx) ·
optional `OPENAI_API_KEY`/`OPENAI_MODEL`.
- **Do not add/modify secrets this phase.** If `OPENAI_API_KEY` is absent, the AI analyzer safely returns
  `skipped` (Phase 6D) — no crash. Email/static/media settings: confirm unchanged.

## 5. Backup plan (run BEFORE pull/migrate — see PHASE_8A_PRODUCTION_ROLLBACK_PLAN.md for full detail)
```bash
# DB (Postgres in the db service)
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backups/pre_deploy_$(date +%Y%m%d_%H%M%S).sql
# Media volume
docker run --rm -v "$(basename "$PWD")_media_volume":/m -v "$PWD/backups":/out alpine \
  tar czf /out/media_pre_deploy_$(date +%Y%m%d_%H%M%S).tgz -C /m .
# Code state (RECORD the rollback commit)
git rev-parse HEAD ; git status --short ; git log --oneline -10
```

## 6. Future deployment sequence (DO NOT EXECUTE this phase)
```bash
ssh root@88.222.220.132
cd /opt/1saudicyber
git status --short ; git branch --show-current ; git log --oneline -10   # record current = rollback
# >>> take DB + media + code backups (Step 5) <<<
git fetch origin
git checkout cybertrust-execution
git pull --ff-only origin cybertrust-execution        # to 5771735
docker compose ps                                     # confirm 'web' + 'db'
docker compose build web
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py migrate          # additive 0012–0015 (+ any earlier)
docker compose run --rm web python manage.py collectstatic --noinput
docker compose up -d --force-recreate web
docker compose ps ; docker compose logs --tail=100 web
curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz/ ; curl -I https://1saudicyber.com/
```
> Service names `web`/`db` are confirmed from the repo's `docker-compose.yml`; still re-confirm on host
> with `docker compose ps` before building. Nginx/SSL/DNS are **not** touched.

## 7. Post-deploy smoke
See **PHASE_8A_PRODUCTION_SMOKE_CHECKLIST.md** (public + authenticated + staff smoke; 417/no-334;
no certification claim; tenant isolation).

## 8. Rollback
See **PHASE_8A_PRODUCTION_ROLLBACK_PLAN.md** (code rollback to the recorded commit; DB restore only if
required; additive tables can be left in place; triggers listed).

## 9. Risk register (summary — full table in this doc § Risk Register below)
R1 missing DB backup · R2 migration failure · R3 service-name mismatch · R4 static not updated ·
R5 no OpenAI key · R6 subscription-gate prod-data differences · R7 prod data lacks relationships ·
R8 cross-company exposure regression · R9 Nginx/proxy/static path · R10 long rebuild downtime.

### Risk register
| ID | Risk | Sev | Prob | Mitigation | Rollback trigger | Owner |
|---|---|---|---|---|---|---|
| R1 | Production DB backup missing | High | Low | Mandatory `pg_dump` gate before migrate; verify file size | N/A (block deploy) | Deployer |
| R2 | Migration failure | High | Low | Additive-only; run `check`+`showmigrations` first; backup taken | migrate errors → restore DB + rollback code | Deployer |
| R3 | Docker service-name mismatch | Med | Low | Confirm `docker compose ps` before build (web/db verified in repo) | build/up fails | Deployer |
| R4 | Static files not updated | Med | Med | `collectstatic --noinput`; WhiteNoise/manifest; restart web | broken assets | Deployer |
| R5 | OpenAI key absent | Low | Med | 6D safe `skipped` state; no crash | none (expected) | Owner |
| R6 | Subscription gate differs on prod data | Med | Low | Smoke reports gated/unlocked paths post-deploy | report exposes gated content | Deployer |
| R7 | Prod data lacks expected relationships | Med | Med | New models are additive/empty initially; journey degrades gracefully | 500s on journey/report | Deployer |
| R8 | Cross-company data exposure regression | High | Low | Tenant-isolation tests green locally; smoke cross-company | any cross-company data visible | Owner |
| R9 | Nginx/proxy/static path mismatch | Med | Low | Do not change Nginx; WEB_PORT 127.0.0.1; verify `/healthz/` via curl | healthz/HTTPS fails | Deployer |
| R10 | Long downtime due to rebuild | Low | Med | Build image, then `up -d --force-recreate web`; off-peak window | extended outage | Owner |

## 10. GO / NO-GO checklist
**GO only if ALL true:**
```
[ ] local branch clean (5771735)         [ ] full local tests pass
[ ] target commit confirmed (5771735)    [ ] production current commit recorded (rollback commit)
[ ] DB backup completed + verified       [ ] media backup completed
[ ] .env verified (no secrets printed)   [ ] migrations reviewed (additive 0012–0015)
[ ] rollback commit recorded             [ ] smoke checklist ready
[ ] deployment window approved           [ ] user explicitly says GO
```
**NO-GO if ANY:** prod git dirty · backup fails · migrations unclear · tests failing · unknown service
names · missing critical env · unreviewed local changes · no rollback plan · user has not approved.

## 11. Out of scope (this phase)
No production deployment, no SSH, no production migration, no service restart, no `.env`/secret change,
no Nginx/DNS/SSL change, no certification issuance, no official accreditation, no payment, no external
connectors, no frontend replacement, no destructive migration, no production data change.
