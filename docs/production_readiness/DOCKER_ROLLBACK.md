# CyberTrust KSA — Docker Rollback

**Status:** Operational runbook. No real deployment is performed here.

## Principle
Roll back the **image/release** first; only roll back the **database** if a migration must be
reverted. Always have a fresh backup before any rollback (see the runbook's Backup section).

## 1. Identify the current and previous release
- Tag images per release (recommended): build with a version tag and record the git commit.
  ```bash
  docker compose build
  docker tag <image> cybertrust-web:<release>      # e.g. the git short SHA
  ```
- Keep the previous known-good tag available locally or in your registry.

## 2. Roll back the application image
```bash
# Point the web service at the previous good image tag (compose override or edited tag),
# then recreate only the web service:
docker compose up -d --no-deps web
docker compose ps          # confirm web is healthy again
curl -fsS http://localhost:${WEB_PORT:-8000}/healthz/
```
If you build from source, check out the previous good commit and rebuild:
```bash
git checkout <previous-good-commit>
docker compose build web && docker compose up -d --no-deps web
```

## 3. Database considerations
- **App-only rollback (no schema change):** no DB action needed — the schema is compatible.
- **If the new release added a migration that must be undone:**
  1. Take a backup first (`pg_dump`).
  2. Reverse the specific migration:
     ```bash
     docker compose exec web python manage.py migrate <app> <previous_migration_name>
     ```
  3. Only restore from a `pg_dump` backup if a migration is not cleanly reversible.
- Phase 3L introduces **no** migrations, so a 3L rollback is image-only.

## 4. Verify
- `docker compose ps` → `web` and `db` healthy.
- `GET /healthz/` returns `{"status":"ok"}`.
- Run the smoke test checklist in `DOCKER_DEPLOYMENT_RUNBOOK.md`.

## 5. Clean up
- Remove failed/dangling images once the rollback is confirmed stable:
  ```bash
  docker image prune -f
  ```
- Do **not** delete `postgres_data`, `static_volume`, or `media_volume` during a rollback.
