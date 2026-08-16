"""Check application dependencies without changing production state."""
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'Verify database, cache/Redis and required async settings for Cyber-5.'

    def handle(self, *args, **options):
        failures = []
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            self.stdout.write('OK database')
        except Exception as exc:
            failures.append('database')
            self.stderr.write(f'FAIL database: {exc}')

        key = f'cyber5:readiness:{timezone.now().timestamp()}'
        try:
            cache.set(key, 'ok', timeout=30)
            if cache.get(key) != 'ok':
                raise RuntimeError('cache round-trip mismatch')
            cache.delete(key)
            self.stdout.write('OK cache')
        except Exception as exc:
            failures.append('cache')
            self.stderr.write(f'FAIL cache: {exc}')

        from django.conf import settings
        enabled = bool(getattr(settings, 'EVIDENCE_ASYNC_ENABLED', False))
        broker = str(getattr(settings, 'CELERY_BROKER_URL', '') or '')
        if enabled and not broker:
            failures.append('celery')
            self.stderr.write('FAIL celery: async evidence is enabled but no broker URL is configured')
        else:
            self.stdout.write('OK celery configuration')

        if failures:
            raise CommandError('Operational readiness failed: ' + ', '.join(failures))
        self.stdout.write(self.style.SUCCESS('READINESS OK'))
