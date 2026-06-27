"""Unit tests for the Smart Deployment Guard (Phase 8F-A).

Pure unittest (no Django DB). Subprocess and HTTP are mocked, so NOTHING real is
deployed, pulled, built, or restarted. Run:

    python -m unittest deployment.tests.test_smart_deploy_guard -v
    # or: python manage.py test deployment.tests.test_smart_deploy_guard
"""
import os
import tempfile
import types
import unittest

from deployment.scripts import smart_deploy as sd


SWITCHER = (
    '<form action="/i18n/setlang/" method="post">'
    '<button type="submit" name="language" value="ar">العربية</button>'
    '<span>|</span>'
    '<button type="submit" name="language" value="en">English</button></form>'
)
SAFE_PUBLIC = '<!DOCTYPE html><html lang="ar" dir="rtl">' + SWITCHER + '417 ضابطًا</html>'
REG_PAGE = SAFE_PUBLIC + 'الرعاية الصحية شروط الاستخدام سياسة الخصوصية'


def make_args(**over):
    d = dict(target='a3e3c99', phase='phase8c_deploy_c', dry_run=False, execute=True,
             project_path='/opt/1saudicyber', domain='https://1saudicyber.com',
             branch='cybertrust-execution', yes=True, report_dir=None,
             backup_base=tempfile.mkdtemp())  # writable temp base for tests
    d.update(over)
    return types.SimpleNamespace(**d)


class FakeRunner:
    """Records commands; returns canned output; simulates backup file creation."""
    def __init__(self, responses=None, db_empty=False, dirty=False, not_ff=False):
        self.responses = responses or {}
        self.calls = []
        self.db_empty = db_empty
        self.dirty = dirty
        self.not_ff = not_ff
        self.backup_dir = None
        self.dry_run = False

    def run(self, cmd, mutating=False, check=True):
        sd.assert_command_safe(cmd)
        self.calls.append({'cmd': cmd, 'mutating': mutating})
        # canned overrides
        for key, val in self.responses.items():
            if key in cmd:
                return val
        # defaults emulating a clean, fast-forwardable, healthy server
        if cmd == 'pwd':
            return 0, '/opt/1saudicyber', ''
        if cmd == 'git branch --show-current':
            return 0, 'cybertrust-execution', ''
        if cmd == 'git status --short':
            return (0, ' M somefile\n', '') if self.dirty else (0, '', '')
        if cmd == 'git rev-parse HEAD':
            return 0, 'a3e3c99deadbeef', ''
        if cmd.startswith('git rev-parse origin/'):
            return 0, 'a3e3c99deadbeef', ''
        if 'merge-base --is-ancestor' in cmd:
            return (1, '', '') if self.not_ff else (0, '', '')
        if cmd == 'docker compose ps':
            return 0, 'web   running\ndb   running', ''
        if cmd.startswith('mkdir -p'):
            self.backup_dir = cmd.split()[-1]
            os.makedirs(self.backup_dir, exist_ok=True)
            return 0, '', ''
        if 'pg_dump' in cmd and '>' in cmd:
            target = cmd.split('>')[-1].strip()
            with open(target, 'w') as f:
                f.write('' if self.db_empty else 'PGDUMP-CONTENT')
            return 0, '', ''
        if 'media_volume_pre_deploy' in cmd:
            # tar target is /backup/<name>; -v <host_dir>:/backup maps it to the host.
            host_dir = None
            for tok in cmd.split():
                if tok.endswith(':/backup'):
                    host_dir = tok.split(':/backup')[0]
            m = sd.re.search(r'/backup/(media_volume_pre_deploy_\S+\.tar\.gz)', cmd)
            if host_dir and m:
                with open(os.path.join(host_dir, m.group(1)), 'w') as f:
                    f.write('TARDATA')
            return 0, '', ''
        if 'docker compose logs' in cmd:
            return 0, 'gunicorn started OK', ''
        return 0, '', ''


def make_fetch(bodies=None, codes=None):
    bodies = bodies or {}
    codes = codes or {}
    def _fetch(url):
        path = url.replace('https://1saudicyber.com', '') or '/'
        code = codes.get(path, 200 if path in (sd.PUBLIC_PATHS + sd.HEALTH_PATHS) else 302)
        body = bodies.get(path, REG_PAGE if 'company' in path else SAFE_PUBLIC)
        return code, body
    return _fetch


def run_guard(args, runner, fetch):
    rd = tempfile.mkdtemp()
    g = sd.SmartDeployGuard(args, runner=runner, fetch=fetch)
    # the guard writes the media file itself? No — FakeRunner does. Ensure media file is non-zero:
    status, path = g.run(rd)
    return g, status, path


# ---- pure helpers ----
class PureHelperTests(unittest.TestCase):
    def test_valid_sha(self):
        self.assertTrue(sd.is_valid_sha('a3e3c99'))
        self.assertTrue(sd.is_valid_sha('a3e3c997fe62cf6068837922802aa9d4f7a0b964'))
        self.assertFalse(sd.is_valid_sha(''))
        self.assertFalse(sd.is_valid_sha('not-a-sha!'))

    def test_forbidden_command_blocked(self):
        for bad in ('git reset --hard HEAD~1', 'docker compose down -v', 'docker volume rm x',
                    'git push --force', 'rm -rf /opt', 'dropdb prod'):
            with self.assertRaises(sd.GateError):
                sd.assert_command_safe(bad)
        self.assertTrue(sd.assert_command_safe('git pull --ff-only origin cybertrust-execution'))

    def test_smoke_status_matrix(self):
        self.assertTrue(sd.smoke_status_ok(200, 'public'))
        self.assertFalse(sd.smoke_status_ok(302, 'public'))
        self.assertTrue(sd.smoke_status_ok(302, 'protected'))
        self.assertTrue(sd.smoke_status_ok(403, 'protected'))
        for bad in (404, 500, 502, 503):
            self.assertFalse(sd.smoke_status_ok(bad, 'public'))
            self.assertFalse(sd.smoke_status_ok(bad, 'protected'))

    def test_leak_detection(self):
        self.assertEqual(sd.find_leaks('clean page'), [])
        self.assertIn('Phase 8C-FIX-C', sd.find_leaks('x Phase 8C-FIX-C y'))

    def test_switcher_present_once(self):
        self.assertTrue(sd.switcher_present_once(SAFE_PUBLIC))
        self.assertFalse(sd.switcher_present_once('<html>no switcher</html>'))
        self.assertFalse(sd.switcher_present_once(SAFE_PUBLIC + SWITCHER))  # duplicate

    def test_unsafe_positive_claims(self):
        self.assertEqual(sd.unsafe_positive_claims('platform'), [])
        self.assertIn('معتمد من NCA', sd.unsafe_positive_claims('نحن معتمد من NCA رسميًا'))
        # negation/disclaimer is allowed
        self.assertEqual(sd.unsafe_positive_claims('لا يُعد اعتماد رسمي من أي جهة'), [])


# ---- arg validation ----
class ArgValidationTests(unittest.TestCase):
    def _guard(self, **over):
        return sd.SmartDeployGuard(make_args(**over), runner=FakeRunner(), fetch=make_fetch())

    def test_requires_exactly_one_mode(self):
        with self.assertRaises(sd.GateError):
            self._guard(dry_run=True, execute=True).validate_args()

    def test_invalid_target_blocks(self):
        with self.assertRaises(sd.GateError):
            self._guard(target='nope!').validate_args()

    def test_execute_requires_yes(self):
        with self.assertRaises(sd.GateError):
            self._guard(execute=True, dry_run=False, yes=False).validate_args()

    def test_valid_execute_args(self):
        self.assertTrue(self._guard().validate_args())


# ---- dry-run never mutates ----
class DryRunTests(unittest.TestCase):
    def test_real_runner_skips_mutating_in_dry_run(self):
        called = {'n': 0}
        import subprocess
        orig = subprocess.run
        subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError('subprocess ran in dry-run mutating'))
        try:
            r = sd.Runner(dry_run=True, log=lambda m: None)
            rc, out, err = r.run('git pull --ff-only origin cybertrust-execution', mutating=True)
            self.assertEqual(rc, 0)  # logged, not executed
        finally:
            subprocess.run = orig


# ---- integration (mocked) ----
class GuardIntegrationTests(unittest.TestCase):
    def _media_after_mkdir(self, runner):
        # FakeRunner's media branch writes a file; ensure it's non-zero by writing here too
        return runner

    def test_happy_path_go(self):
        g, status, path = run_guard(make_args(), FakeRunner(), make_fetch())
        self.assertIn(status, ('GO', 'GO_WITH_NOTES'))
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding='utf-8') as f:
            self.assertIn('Final status', f.read())

    def test_dirty_git_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(dirty=True), make_fetch())
        self.assertEqual(status, 'NO_GO')

    def test_non_fast_forward_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(not_ff=True), make_fetch())
        self.assertEqual(status, 'NO_GO')

    def test_zero_byte_db_backup_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(db_empty=True), make_fetch())
        self.assertEqual(status, 'NO_GO')
        self.assertTrue(any('DB backup' in n for n in g.notes))

    def test_smoke_500_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(), make_fetch(codes={'/login/': 500}))
        self.assertEqual(status, 'NO_GO')

    def test_leak_text_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(),
                                 make_fetch(bodies={'/': SAFE_PUBLIC + 'Phase 8C-FIX-C reusable public'}))
        self.assertEqual(status, 'NO_GO')

    def test_missing_switcher_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(),
                                 make_fetch(bodies={'/': '<html>no switcher 417</html>'}))
        self.assertEqual(status, 'NO_GO')

    def test_unsafe_certification_blocks(self):
        g, status, _ = run_guard(make_args(), FakeRunner(),
                                 make_fetch(bodies={'/': SAFE_PUBLIC + ' معتمد من NCA رسميًا'}))
        self.assertEqual(status, 'NO_GO')

    def test_report_file_generated(self):
        g, status, path = run_guard(make_args(phase='unit_phase'), FakeRunner(), make_fetch())
        self.assertTrue(path.endswith('.md'))
        self.assertIn('smart_deploy_unit_phase_', path)


if __name__ == '__main__':
    unittest.main()
