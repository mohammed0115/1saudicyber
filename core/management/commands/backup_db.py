"""
DD-fix (ops) — database backup command (for cron).

Dumps the configured database to BACKUP_DIR (env BACKUP_DIR, default ./backups) with a
timestamped filename, and prunes dumps older than --keep-days. PostgreSQL uses pg_dump;
SQLite copies the file. Schedule in cron, e.g.:  manage.py backup_db --keep-days 14
"""
import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Back up the database (pg_dump for Postgres, file copy for SQLite) with rotation.'

    def add_arguments(self, parser):
        parser.add_argument('--keep-days', type=int, default=14,
                            help='Delete backups older than this many days (default 14).')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        backup_dir = os.getenv('BACKUP_DIR', str(settings.BASE_DIR / 'backups'))
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')  # noqa: DTZ005 (local ok for filenames)
        engine = db.get('ENGINE', '')

        if 'postgresql' in engine:
            out = os.path.join(backup_dir, 'db-%s.sql.gz' % stamp)
            env = dict(os.environ, PGPASSWORD=db.get('PASSWORD', ''))
            cmd = ['pg_dump', '-h', db.get('HOST', 'localhost'), '-p', str(db.get('PORT', '5432')),
                   '-U', db.get('USER', ''), '-d', db.get('NAME', '')]
            with open(out, 'wb') as fh:
                p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env)
                p2 = subprocess.Popen(['gzip'], stdin=p1.stdout, stdout=fh)
                p1.stdout.close()
                p2.communicate()
            self.stdout.write('PostgreSQL backup written: %s' % out)
        elif 'sqlite' in engine:
            src = str(db.get('NAME', ''))
            if src in (':memory:', '') or not os.path.exists(src):
                self.stderr.write('SQLite DB is in-memory or missing; nothing to back up.')
                return
            out = os.path.join(backup_dir, 'db-%s.sqlite3' % stamp)
            shutil.copy2(src, out)
            self.stdout.write('SQLite backup written: %s' % out)
        else:
            self.stderr.write('Unsupported DB engine for backup: %s' % engine)
            return

        # Rotation: prune old dumps.
        cutoff = datetime.now().timestamp() - options['keep_days'] * 86400  # noqa: DTZ005
        pruned = 0
        for name in os.listdir(backup_dir):
            path = os.path.join(backup_dir, name)
            if name.startswith('db-') and os.path.getmtime(path) < cutoff:
                os.remove(path)
                pruned += 1
        self.stdout.write('Backup complete. Pruned %d old file(s).' % pruned)
