"""Static tests for the Unified Safe Deployment Script (Phase 8D-3A-TOOLING).

Pure unittest. These tests ONLY read the script file as text and assert its
content/structure — they NEVER execute it, so nothing is deployed, pulled,
built, migrated, or restarted, and no production resource is touched. Run:

    python -m unittest deployment.tests.test_safe_manual_deploy_script -v
    # or: python manage.py test deployment.tests.test_safe_manual_deploy_script
"""
import os
import stat
import unittest

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'deployment', 'scripts', 'safe_manual_deploy.sh',
)


def _read():
    with open(SCRIPT_PATH, encoding='utf-8') as f:
        return f.read()


class SafeManualDeployScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read()

    # ---- existence / executability ----
    def test_script_file_exists(self):
        self.assertTrue(os.path.isfile(SCRIPT_PATH), SCRIPT_PATH)

    def test_executable_or_bash_shebang(self):
        first_line = self.src.splitlines()[0]
        mode = os.stat(SCRIPT_PATH).st_mode
        is_exec = bool(mode & stat.S_IXUSR)
        self.assertTrue(is_exec or first_line.startswith('#!') and 'bash' in first_line,
                        'script must be executable or have a bash shebang')

    def test_has_bash_shebang(self):
        self.assertTrue(self.src.splitlines()[0].startswith('#!'))
        self.assertIn('bash', self.src.splitlines()[0])

    def test_uses_strict_mode(self):
        self.assertIn('set -euo pipefail', self.src)

    # ---- required arguments ----
    def test_contains_required_arguments(self):
        for arg in ('--target', '--phase', '--branch', '--domain', '--project-path',
                    '--dry-run', '--yes'):
            self.assertIn(arg, self.src, arg)

    def test_execute_requires_yes(self):
        # Without --yes, execute mode must refuse.
        self.assertIn('ASSUME_YES', self.src)
        self.assertIn('requires --yes', self.src)

    def test_dry_run_is_non_mutating(self):
        self.assertIn('DRY_RUN', self.src)
        self.assertIn('(dry-run) would run', self.src)

    # ---- safety gates ----
    def test_git_clean_gate(self):
        self.assertIn('git status --short', self.src)
        self.assertIn('working tree is not clean', self.src)

    def test_branch_gate(self):
        self.assertIn('git branch --show-current', self.src)

    def test_target_equals_origin_gate(self):
        self.assertIn('origin/${BRANCH}', self.src)
        self.assertIn('merge-base --is-ancestor', self.src)

    def test_db_backup_nonzero_gate(self):
        self.assertIn('pg_dump', self.src)
        self.assertIn('pre_deploy_${STAMP}.sql', self.src)
        self.assertIn('test -s "$DB_BACKUP_PATH"', self.src)

    def test_media_backup_nonzero_gate(self):
        self.assertIn('media_volume_pre_deploy_${STAMP}.tar.gz', self.src)
        self.assertIn('test -s "$MEDIA_BACKUP_PATH"', self.src)

    def test_ff_only_pull(self):
        self.assertIn('git pull --ff-only origin', self.src)

    def test_deploy_commands_present(self):
        for cmd in ('docker compose build web',
                    'manage.py check',
                    'makemigrations --check --dry-run',
                    'manage.py migrate',
                    'manage.py collectstatic --noinput',
                    'docker compose up -d --force-recreate web'):
            self.assertIn(cmd, self.src, cmd)

    # ---- smoke / leak / claims ----
    def test_smoke_urls_present(self):
        for path in ('/healthz/', '/login/', '/privacy/', '/terms/',
                     '/auditors/register/', '/platform-admin/auditors/',
                     '/compliance/classification/', '/compliance/dashboard/'):
            self.assertIn(path, self.src, path)

    def test_smoke_rejects_5xx_and_404(self):
        # The smoke matcher must treat 500/502/503/404 as failures.
        self.assertIn('500|502|503|504|404', self.src)

    def test_leak_scan_tokens_present(self):
        for token in ('Phase 8C-FIX-C', 'reusable public', 'msgid', '{% trans'):
            self.assertIn(token, self.src, token)

    def test_unsafe_claims_scan_terms_present(self):
        for term in ('معتمد من NCA', 'اعتماد رسمي', 'certified by NCA',
                     'official accreditation', 'government accredited'):
            self.assertIn(term, self.src, term)

    def test_claims_scan_allows_negated_disclaimer(self):
        # Conservative negation handling must be present.
        self.assertIn('لا|ليس|دون|بدون', self.src)

    # ---- report + rollback ----
    def test_writes_report(self):
        self.assertIn('safe_manual_deploy_${PHASE}_${STAMP}.md', self.src)
        self.assertIn('Manual rollback instructions', self.src)

    def test_does_not_auto_rollback(self):
        # No automatic 'git checkout <rollback>' executed by the script flow:
        # rollback only appears inside the printed instructions block.
        self.assertNotIn('run_mutating git checkout', self.src)

    # ---- must never run QA seed / destructive ops ----
    def test_never_invokes_qa_seed(self):
        self.assertNotIn('seed_manus_e2e_qa', self.src)

    def test_no_destructive_volume_or_reset(self):
        for danger in ('down -v', 'volume rm', 'reset --hard', 'push --force', 'dropdb'):
            self.assertNotIn(danger, self.src, danger)


if __name__ == '__main__':
    unittest.main()
