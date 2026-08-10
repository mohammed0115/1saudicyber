# Phase 8A — Production Rollback Plan

> PLANNING ONLY. Commands below are for a future, owner-approved execution on the server. Nothing here
> is executed in this phase. Path `/opt/1saudicyber`, services `web`/`db` (confirm with `docker compose ps`).

## 0. Prerequisite recorded at deploy time
Before pulling, the deployer MUST record the **rollback commit** (production's current HEAD):
```bash
cd /opt/1saudicyber
git rev-parse HEAD            # → <ROLLBACK_COMMIT>
git log --oneline -10
git status --short            # must be clean; if dirty → reconcile before deploy
```
And confirm backups exist (DB dump + media tgz) from the deployment plan Step 5.

## 1. Code rollback (preferred — for code-only issues)
Because the new migrations (`compliance/0012–0015`) are **additive** (CreateModel only), a code-only
rollback is safe: the new tables simply go unused by the older code.
```bash
cd /opt/1saudicyber
git checkout <ROLLBACK_COMMIT>          # or: git reset --hard <ROLLBACK_COMMIT>  (use cautiously)
docker compose build web
docker compose up -d --force-recreate web
docker compose ps ; docker compose logs --tail=100 web
curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz/
```

## 2. Database rollback (only if a data/schema issue requires it)
```
- If the issue is code-only  → rollback code (§1), LEAVE the additive tables in place.
- If the issue requires DB   → restore the pre-deploy backup:
```
```bash
# Restore into the running, intended-empty/consistent db service
cat backups/pre_deploy_<STAMP>.sql | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```
> **Do NOT manually drop tables** unless explicitly approved by the owner. Additive tables are harmless
> when unused.

## 3. Media rollback (if media volume affected)
```bash
docker run --rm -v "$(basename "$PWD")_media_volume":/m -v "$PWD/backups":/in alpine \
  sh -c "cd /m && tar xzf /in/media_pre_deploy_<STAMP>.tgz"
```

## 4. Static rollback (if assets break)
```bash
docker compose run --rm web python manage.py collectstatic --noinput
docker compose restart web
```

## 5. Rollback decision triggers (any → roll back)
```
/healthz/ fails or non-200
login fails
500 errors on dashboard / journey / reports
migrate fails or leaves DB inconsistent
static files badly broken
tenant-isolation issue (company A sees company B data)
auditor-reviewed report exposes cross-company data
any official certification / accreditation claim appears in UI
legacy 334 shown as the current official total
```

## 6. Post-rollback verification
```bash
docker compose ps
curl -fsS http://127.0.0.1:${WEB_PORT:-8000}/healthz/
curl -I https://cyber-5.com/
# re-run the smoke checklist (PHASE_8A_PRODUCTION_SMOKE_CHECKLIST.md)
```
Record outcome and notify the owner. If rollback also fails, escalate and keep the service in the last
known-good state (do not iterate blindly on production).
