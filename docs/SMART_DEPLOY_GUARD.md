# Smart Deployment Guard

> **Phase 8F-A.** A reusable, stdlib-only Python guard that automates the repeated
> 1SaudiCyber production deployment checklist with hard safety gates. It is a **tool**, not
> a deployment — running it in `--dry-run` changes nothing.

## Purpose
Reduce human error across the repeated manual deploys (8C-DEPLOY-A/B/C) by encoding the full
checklist once: **preflight → backup → fast-forward pull → docker build → Django checks →
no-migration verification → collectstatic → restart web → smoke tests → leak/switcher/UX/legal
verification → logs → report.** It stops on the first failed safety gate and writes a Markdown report.

- **Script:** `deployment/scripts/smart_deploy.py`
- **Tests:** `deployment/tests/test_smart_deploy_guard.py`
- **Reports:** `deployment/reports/smart_deploy_<phase>_<timestamp>.md` (gitignored output)

## Safe usage
The script is stdlib-only (no Django import) so it can be copied to the server and run there.
**Always run `--dry-run` first** and read the printed plan + report before `--execute`.

### Dry-run (no changes)
```bash
python deployment/scripts/smart_deploy.py \
  --target a3e3c99 --phase phase8c_deploy_c --dry-run
```
Dry-run validates arguments, previews every step, **logs** (never runs) all mutating commands
(`git pull`, `docker build`, `migrate`, `collectstatic`, `up --force-recreate`, backups), and never
aborts just because docker/path differ locally.

### Execute (real deploy — run ON the server, with approval)
```bash
python deployment/scripts/smart_deploy.py \
  --target a3e3c99 --phase phase8c_deploy_c --execute --yes \
  --project-path /opt/1saudicyber --branch cybertrust-execution \
  --domain https://1saudicyber.com
```
`--execute` requires `--yes`. It runs the real checklist and **stops on the first failed gate**,
printing the manual rollback commands.

## Required server context (execute mode)
- Run from `/opt/1saudicyber` (the project path), on branch `cybertrust-execution`, with a **clean**
  git tree.
- Docker Compose services `web` and `db` present and running.
- Origin `cybertrust-execution` already contains the `--target` commit (push happens separately).
- Backup base `--backup-base` writable (default `/root/1saudicyber-deploy-backups`).

## CLI arguments
| Arg | Required | Default |
|---|---|---|
| `--target <sha>` | yes (7–40 hex) | — |
| `--phase <name>` | yes | — |
| `--dry-run` / `--execute` | exactly one | — |
| `--yes` | required with `--execute` | off |
| `--project-path` | no | `/opt/1saudicyber` |
| `--branch` | no | `cybertrust-execution` |
| `--domain` | no | `https://1saudicyber.com` |
| `--backup-base` | no | `/root/1saudicyber-deploy-backups` |
| `--report-dir` | no | `deployment/reports` |

## What it checks (safety gates → NO_GO on failure)
- Exactly one mode; valid `--target` SHA; `--execute` needs `--yes`.
- Current path == project path; branch == expected; **git tree clean**.
- `git fetch` + `merge-base --is-ancestor HEAD origin/branch` → pull is **fast-forward only**.
- **DB backup** exists and is **> 0 bytes**; **media backup** exists (tiny tar allowed for an empty
  volume; fails only if missing/zero).
- HEAD after pull equals `--target`; tree still clean.
- `docker compose build web`; `manage.py check`; `makemigrations --check` → **No changes** (any
  detected migration → stop); `migrate`.
- `collectstatic`; `up -d --force-recreate web`; web logs free of `Traceback / TemplateSyntaxError /
  ImportError / ModuleNotFoundError`.
- **Smoke:** public `/` `/login/` `/get-started*` → 200; protected → 302/403; **fail on 404/500/502/503**.
- **Leak check:** "Phase 8C-FIX-C", "reusable public", "Posts to Django", "RTL/LTR safe" absent on
  public pages.
- **Language switcher:** present **exactly once** per public page (`/i18n/setlang`, `name="language"`,
  `value="ar"`/`value="en"`); login not duplicated.
- **UX/trust:** Arabic registration labels, terms/privacy, auditor wording, "جاهزية للمراقبة المستمرة",
  "مؤشرات توضيحية", `417` present; `334` not shown as the current total.
- **Legal sweep:** "معتمد من NCA/أرامكو/سابك", "اعتماد رسمي/حكومي", "certified by NCA",
  "official accreditation", "government accredited" must be absent **as positive claims** (allowed only
  inside a negation/disclaimer like "لا يُعد …").

## What it refuses to do
It **never constructs or runs** destructive commands: `git reset --hard`, `git push --force`/`-f`,
`docker compose down -v`, `docker volume rm`, `dropdb`, `DROP TABLE`, `rm -rf`, `.env` edits, or
nginx/certbot/DNS changes. `assert_command_safe()` blocks them; `--force-recreate` is explicitly allowed
(only force-*push* is blocked). It performs no deployment in `--dry-run`.

## Rollback
The guard **does not auto-rollback** (see below). On failure it prints the manual rollback block, using
the pre-deploy HEAD it recorded as the rollback commit:
```bash
cd /opt/1saudicyber
git checkout <ROLLBACK_COMMIT>
docker compose build web
docker compose up -d --force-recreate web
sleep 30
docker compose ps
curl -I https://1saudicyber.com/healthz/
# DB restore is NOT needed (no migrations); restore from backup only on a real DB incident.
```

## Known limitations / why no auto-rollback yet
- **No auto-rollback:** rolling back automatically on a transient smoke blip could thrash production;
  a human should confirm. An explicit `--auto-rollback` flag can be added later once trusted.
- It assumes the Compose service names `web`/`db` and the `1saudicyber_media_volume` volume; verify with
  `docker compose ps`/`docker volume ls` if the environment differs.
- The Docker entrypoint may itself run migrate/collectstatic before each command — recorded as a note,
  not a failure.
- HTTP smoke tolerates self-signed certs (curl `-k` parity); it checks status + content, not pixels.
  Visual/mobile QA stays a separate (browser) phase.

## Tests
```bash
python -m unittest deployment.tests.test_smart_deploy_guard -v
# or
python manage.py test deployment.tests.test_smart_deploy_guard
```
20 tests (subprocess + HTTP mocked — nothing real is deployed): arg validation, dry-run skips mutating
commands, forbidden-command blocking, dirty-tree/non-FF/zero-byte-backup/smoke-500/leak/missing-switcher/
unsafe-claim all → NO_GO, and report generation.
