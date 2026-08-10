#!/usr/bin/env python3
"""
Smart Deployment Guard for Cyber-5 (Phase 8F-A).

Automates the repeated production deployment checklist with hard safety gates:
  preflight -> backup -> fast-forward pull -> docker build -> Django checks ->
  no-migration verification -> collectstatic -> restart web -> smoke tests ->
  leak/switcher/UX/legal verification -> logs -> report.

Two modes:
  --dry-run   : validate + print what WOULD happen; never runs mutating commands.
  --execute   : run the real checklist; requires --yes; stops on the first failed gate.

Stdlib only (no Django import) so it can run standalone on the server. It NEVER
runs destructive commands (reset --hard, push --force, down -v, volume rm, dropdb,
DROP TABLE, rm -rf) and never edits secrets/.env/nginx/DNS. It does NOT auto-rollback
— on failure it prints the rollback commands only.
"""
import argparse
import datetime
import os
import re
import shlex
import ssl
import subprocess
import sys
import urllib.request

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
DEFAULT_PROJECT_PATH = '/opt/1saudicyber'
DEFAULT_BRANCH = 'cybertrust-execution'
DEFAULT_DOMAIN = 'https://cyber-5.com'

# Commands that must NEVER be constructed/run by this guard.
# NOTE: 'push --force'/'push -f' (not bare 'force', so '--force-recreate' stays allowed).
FORBIDDEN_COMMAND_SUBSTRINGS = [
    'reset --hard', 'push --force', 'push -f', '--force-with-lease',
    'down -v', 'volume rm', 'dropdb', 'drop table', 'rm -rf',
    '> .env', 'nginx', 'certbot',
]

PUBLIC_PATHS = ['/', '/login/', '/get-started/', '/get-started/company/', '/get-started/auditor/']
PROTECTED_PATHS = ['/dashboard/', '/compliance/dashboard/', '/compliance/classification/',
                   '/compliance/applicability/', '/compliance/reports/',
                   '/compliance/reports/auditor-reviewed/', '/monitoring/continuous/']
HEALTH_PATHS = ['/healthz/']

LEAK_STRINGS = ['Phase 8C-FIX-C', 'reusable public', 'Posts to Django', 'RTL/LTR safe']
SWITCHER_REQUIRED = ['/i18n/setlang', 'name="language"', 'value="ar"', 'value="en"']
UX_EXPECTED = ['الرعاية الصحية', 'متناهية الصغر', 'شروط الاستخدام', 'سياسة الخصوصية',
               'مدقّق أو مراجع امتثال', 'جاهزية للمراقبة المستمرة', 'مؤشرات توضيحية', '417']
UNSAFE_POSITIVE_CLAIMS = ['معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد رسمي',
                          'اعتماد حكومي', 'certified by NCA', 'official accreditation', 'government accredited']
NEGATION_MARKERS = ['لا يُعد', 'لا يُعَد', 'وليست', 'ليست', 'does not', 'is not', 'not an official', 'not a final']
FATAL_LOG_MARKERS = ['Traceback', 'TemplateSyntaxError', 'ImportError', 'ModuleNotFoundError']


class GateError(Exception):
    """Raised when a safety gate fails."""


# ----------------------------------------------------------------------------
# Pure validation helpers (unit-tested without subprocess)
# ----------------------------------------------------------------------------
def is_valid_sha(value):
    return bool(value) and bool(re.fullmatch(r'[0-9a-fA-F]{7,40}', value.strip()))


def assert_command_safe(cmd):
    """Raise GateError if a command string contains a forbidden/destructive pattern."""
    low = cmd.lower()
    for bad in FORBIDDEN_COMMAND_SUBSTRINGS:
        if bad in low:
            raise GateError(f'Refusing to run forbidden command pattern {bad!r}: {cmd}')
    return True


def backup_file_ok(path):
    """A backup is OK iff it exists and is non-zero bytes (tiny media tar is allowed)."""
    return os.path.isfile(path) and os.path.getsize(path) > 0


def smoke_status_ok(code, kind):
    """kind in {'public','protected','health'}. Always fail on 404/500/502/503."""
    code = int(code)
    if code in (404, 500, 502, 503):
        return False
    if kind == 'public':
        return code == 200
    if kind == 'health':
        return code == 200
    if kind == 'protected':
        return code in (200, 302, 403)
    return False


def find_leaks(html):
    return [s for s in LEAK_STRINGS if s in html]


def switcher_present_once(html):
    """True if every required marker is present and there is exactly one ar button."""
    if not all(m in html for m in SWITCHER_REQUIRED):
        return False
    return html.count('name="language" value="ar"') == 1


def unsafe_positive_claims(html):
    """Return unsafe claims that appear OUTSIDE a negation/disclaimer context."""
    hits = []
    for claim in UNSAFE_POSITIVE_CLAIMS:
        idx = 0
        while True:
            i = html.find(claim, idx)
            if i < 0:
                break
            ctx = html[max(0, i - 40):i]
            if not any(neg in ctx for neg in NEGATION_MARKERS):
                hits.append(claim)
                break
            idx = i + 1
    return sorted(set(hits))


def shows_legacy_total_as_current(html):
    """Heuristic: 334 rendered as a standalone displayed figure (e.g. >334<)."""
    return '>334<' in html or '334 ضابط' in html


# ----------------------------------------------------------------------------
# Runner (injectable for tests)
# ----------------------------------------------------------------------------
class Runner:
    """Runs shell commands. In dry-run, mutating commands are logged, not executed."""

    def __init__(self, dry_run=True, cwd=None, log=None):
        self.dry_run = dry_run
        self.cwd = cwd
        self.calls = []                 # recorded for tests/report
        self._log = log or (lambda m: print(m))

    def run(self, cmd, mutating=False, check=True):
        assert_command_safe(cmd)
        self.calls.append({'cmd': cmd, 'mutating': mutating, 'dry_run': self.dry_run})
        if self.dry_run and mutating:
            self._log(f'[DRY-RUN] would run: {cmd}')
            return 0, '', ''
        # In dry-run, read-only commands are previewed best-effort and never abort
        # the run (a missing docker / different path must not crash the preview).
        if self.dry_run:
            check = False
        self._log(f'$ {cmd}')
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=self.cwd, capture_output=True, text=True)
        except (FileNotFoundError, OSError) as e:
            if self.dry_run:
                return 127, '', str(e)
            raise GateError(f'Command not runnable: {cmd}\n{e}')
        if check and proc.returncode != 0:
            raise GateError(f'Command failed ({proc.returncode}): {cmd}\n{proc.stderr.strip()}')
        return proc.returncode, proc.stdout, proc.stderr


def http_fetch(url, timeout=15):
    """Return (status_code, body). Tolerant of self-signed certs (curl -k parity)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'smart-deploy-guard'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.getcode(), resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            pass
        return e.code, body


# ----------------------------------------------------------------------------
# Guard
# ----------------------------------------------------------------------------
class SmartDeployGuard:
    def __init__(self, args, runner=None, fetch=None, now=None):
        self.args = args
        self.runner = runner or Runner(dry_run=args.dry_run, cwd=args.project_path)
        self.fetch = fetch or http_fetch
        self.now = now or datetime.datetime.now
        self.stamp = self.now().strftime('%Y%m%d_%H%M%S')
        self.start = self.now().isoformat(timespec='seconds')
        self.notes = []
        self.smoke_rows = []
        self.rollback_commit = None
        self.head_before = None
        self.head_after = None
        self.status = 'GO'
        self.backup_dir = None

    def note(self, msg):
        self.notes.append(msg)

    def fail(self, msg):
        self.status = 'NO_GO'
        raise GateError(msg)

    # ---- argument / preflight gates ----
    def validate_args(self):
        if bool(self.args.dry_run) == bool(self.args.execute):
            raise GateError('Exactly one of --dry-run or --execute is required.')
        if not is_valid_sha(self.args.target or ''):
            raise GateError(f'Invalid --target commit format: {self.args.target!r}')
        if self.args.execute and not self.args.yes:
            raise GateError('--execute requires --yes confirmation.')
        if not self.args.phase:
            raise GateError('--phase is required.')
        return True

    def preflight(self):
        # path
        rc, out, _ = self.runner.run('pwd')
        cwd = (out.strip() or self.args.project_path)
        if not self.args.dry_run and os.path.realpath(self.args.project_path) != os.path.realpath(cwd):
            self.fail(f'Current path {cwd} != project path {self.args.project_path}')
        # branch
        _, branch, _ = self.runner.run('git branch --show-current')
        branch = branch.strip()
        if not self.args.dry_run and branch != self.args.branch:
            self.fail(f'Branch {branch!r} != expected {self.args.branch!r}')
        # clean tree
        _, status, _ = self.runner.run('git status --short')
        if not self.args.dry_run and status.strip():
            self.fail(f'Git tree is dirty:\n{status}')
        # rollback commit = current HEAD
        _, head, _ = self.runner.run('git rev-parse HEAD')
        self.head_before = head.strip()
        self.rollback_commit = self.head_before
        # docker services
        _, ps, _ = self.runner.run('docker compose ps')
        if not self.args.dry_run and ('web' not in ps or 'db' not in ps):
            self.note('docker compose ps did not clearly show web/db — verify manually.')
        return True

    def fast_forward_check(self):
        self.runner.run('git fetch origin', mutating=False)
        _, origin, _ = self.runner.run(f'git rev-parse origin/{self.args.branch}')
        # HEAD must be an ancestor of origin/branch (pull is fast-forward)
        rc, _, _ = self.runner.run(
            f'git merge-base --is-ancestor HEAD origin/{self.args.branch}', check=False)
        if not self.args.dry_run and rc != 0:
            self.fail('Pull would NOT be fast-forward (HEAD is not an ancestor of origin).')
        return True

    # ---- mutating steps (skipped/logged in dry-run) ----
    def backup(self):
        base = getattr(self.args, 'backup_base', None) or '/root/1saudicyber-deploy-backups'
        self.backup_dir = f'{base}/{self.args.phase}_{self.stamp}'
        self.runner.run(f'mkdir -p {self.backup_dir}', mutating=True)
        db = f'{self.backup_dir}/pre_deploy_{self.stamp}.sql'
        media = f'{self.backup_dir}/media_volume_pre_deploy_{self.stamp}.tar.gz'
        self.runner.run(
            f"docker compose exec -T db sh -c 'pg_dump -U \"$POSTGRES_USER\" \"$POSTGRES_DB\"' > {db}",
            mutating=True)
        self.runner.run(
            "docker run --rm -v 1saudicyber_media_volume:/media:ro "
            f"-v {self.backup_dir}:/backup postgres:16-alpine "
            f"sh -c \"tar -czf /backup/media_volume_pre_deploy_{self.stamp}.tar.gz -C /media .\"",
            mutating=True)
        if not self.args.dry_run:
            if not backup_file_ok(db):
                self.fail(f'DB backup missing or zero bytes: {db}')
            if not os.path.isfile(media) or os.path.getsize(media) == 0:
                self.fail(f'Media backup missing or zero bytes: {media}')
            if os.path.getsize(media) < 1024:
                self.note(f'Media backup is small ({os.path.getsize(media)} bytes) — likely empty volume (OK).')
        return True

    def pull(self):
        self.runner.run(f'git pull --ff-only origin {self.args.branch}', mutating=True)
        _, head, _ = self.runner.run('git rev-parse HEAD')
        self.head_after = head.strip()
        if not self.args.dry_run:
            if not self.head_after.startswith(self.args.target) and self.head_after != self.args.target:
                self.fail(f'HEAD after pull {self.head_after} != target {self.args.target}')
            _, status, _ = self.runner.run('git status --short')
            if status.strip():
                self.fail('Git tree dirty after pull.')
        return True

    def build_and_check(self):
        self.runner.run('docker compose build web', mutating=True)
        self.runner.run('docker compose run --rm web python manage.py check', mutating=True)
        rc, out, err = self.runner.run(
            'docker compose run --rm web python manage.py makemigrations --check --dry-run',
            mutating=True, check=False)
        if not self.args.dry_run and rc != 0:
            self.fail('makemigrations --check detected changes (unexpected migration).')
        self.runner.run('docker compose run --rm web python manage.py migrate', mutating=True)
        self.note('Docker entrypoint may run migrate/collectstatic before the command (known behavior).')
        return True

    def static_and_restart(self):
        self.runner.run('docker compose run --rm web python manage.py collectstatic --noinput', mutating=True)
        self.runner.run('docker compose up -d --force-recreate web', mutating=True)
        rc, logs, _ = self.runner.run('docker compose logs --tail=160 web', check=False)
        if not self.args.dry_run:
            fatal = [m for m in FATAL_LOG_MARKERS if m in logs]
            if fatal:
                self.fail(f'Fatal markers in web logs: {fatal}')
        return True

    # ---- verification (read-only HTTP) ----
    def smoke(self):
        if self.args.dry_run:
            self.note('Smoke tests are run live in --execute mode only.')
            return True
        for path in HEALTH_PATHS + PUBLIC_PATHS + PROTECTED_PATHS:
            kind = 'health' if path in HEALTH_PATHS else ('public' if path in PUBLIC_PATHS else 'protected')
            code, _ = self.fetch(self.args.domain.rstrip('/') + path)
            ok = smoke_status_ok(code, kind)
            self.smoke_rows.append((path, code, kind, 'OK' if ok else 'FAIL'))
            if not ok:
                self.fail(f'Smoke FAIL {code} for {path} ({kind})')
        return True

    def verify_public_pages(self):
        if self.args.dry_run:
            self.note('Leak/switcher/UX/legal verification runs live in --execute mode only.')
            return True
        for path in PUBLIC_PATHS:
            code, body = self.fetch(self.args.domain.rstrip('/') + path)
            leaks = find_leaks(body)
            if leaks:
                self.fail(f'Public leak text {leaks} on {path}')
            if not switcher_present_once(body):
                self.fail(f'Language switcher missing or duplicated on {path}')
            unsafe = unsafe_positive_claims(body)
            if unsafe:
                self.fail(f'Unsafe positive certification/accreditation claim {unsafe} on {path}')
            if shows_legacy_total_as_current(body):
                self.fail(f'Legacy total 334 shown as current on {path}')
        # UX presence on the registration page
        _, reg = self.fetch(self.args.domain.rstrip('/') + '/get-started/company/')
        missing = [s for s in ('الرعاية الصحية', 'شروط الاستخدام', '417') if s not in reg and s != '417']
        if missing:
            self.note(f'UX strings not found on register page: {missing}')
        return True

    # ---- report ----
    def rollback_block(self):
        rb = self.rollback_commit or '<ROLLBACK_COMMIT>'
        return (
            f"cd {self.args.project_path}\n"
            f"git checkout {rb}\n"
            "docker compose build web\n"
            "docker compose up -d --force-recreate web\n"
            "sleep 30\n"
            "docker compose ps\n"
            f"curl -I {self.args.domain.rstrip('/')}/healthz/\n"
            "# DB restore is NOT needed (no migrations); only restore from backup on a real DB incident.")

    def render_report(self):
        end = self.now().isoformat(timespec='seconds')
        rows = '\n'.join(f'| {p} | {c} | {k} | {r} |' for p, c, k, r in self.smoke_rows) or '| (dry-run — not executed) | | | |'
        notes = '\n'.join(f'- {n}' for n in self.notes) or '- none'
        return f"""# Smart Deploy Report — {self.args.phase}

- **mode:** {'dry-run' if self.args.dry_run else 'execute'}
- **target commit:** {self.args.target}
- **rollback commit:** {self.rollback_commit}
- **branch:** {self.args.branch} · **domain:** {self.args.domain} · **path:** {self.args.project_path}
- **start:** {self.start} · **end:** {end}
- **git HEAD before:** {self.head_before} · **after:** {self.head_after}
- **backup dir:** {self.backup_dir}

## Smoke results
| path | code | kind | result |
|---|---|---|---|
{rows}

## Verification
- leak verification: {'run live in execute' if self.args.dry_run else 'passed (no leak text)'}
- language switcher: {'run live in execute' if self.args.dry_run else 'present exactly once per public page'}
- UX/trust strings: {'run live in execute' if self.args.dry_run else 'checked'}
- legal safety sweep: {'run live in execute' if self.args.dry_run else 'no positive certification/accreditation claims'}

## Notes
{notes}

## Final status
{self.status}

## Rollback (manual — guard never auto-rolls-back)
```
{self.rollback_block()}
```
"""

    def write_report(self, report_dir):
        os.makedirs(report_dir, exist_ok=True)
        path = os.path.join(report_dir, f'smart_deploy_{self.args.phase}_{self.stamp}.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.render_report())
        return path

    # ---- orchestration ----
    def run(self, report_dir):
        try:
            self.validate_args()
            self.preflight()
            self.fast_forward_check()
            self.backup()
            self.pull()
            self.build_and_check()
            self.static_and_restart()
            self.smoke()
            self.verify_public_pages()
            if self.status == 'GO' and self.notes:
                self.status = 'GO_WITH_NOTES'
        except GateError as e:
            self.status = 'NO_GO'
            self.note(f'GATE FAILURE: {e}')
        path = self.write_report(report_dir)
        return self.status, path


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def build_arg_parser():
    p = argparse.ArgumentParser(description='Cyber-5 Smart Deployment Guard')
    p.add_argument('--target', required=True, help='target commit SHA (7-40 hex)')
    p.add_argument('--phase', required=True, help='phase name (used in backup/report names)')
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--execute', action='store_true')
    p.add_argument('--project-path', default=DEFAULT_PROJECT_PATH)
    p.add_argument('--domain', default=DEFAULT_DOMAIN)
    p.add_argument('--branch', default=DEFAULT_BRANCH)
    p.add_argument('--yes', action='store_true', help='required for --execute')
    p.add_argument('--backup-base', default='/root/1saudicyber-deploy-backups')
    p.add_argument('--report-dir', default=os.path.join(os.path.dirname(__file__), '..', 'reports'))
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    guard = SmartDeployGuard(args)
    status, report_path = guard.run(os.path.abspath(args.report_dir))
    print(f'\nFINAL STATUS: {status}')
    print(f'REPORT: {report_path}')
    return 0 if status in ('GO', 'GO_WITH_NOTES') else 2


if __name__ == '__main__':
    sys.exit(main())
