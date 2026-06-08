"""
Apply data-retention policies (NFR-047): delete records older than the configured horizon.
Run from cron:  python manage.py purge_expired_data
"""
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Purge data older than the configured retention periods.'

    def handle(self, *args, **options):
        ret = getattr(settings, 'DATA_RETENTION_DAYS', {})
        now = timezone.now()
        deleted = {}

        from core.models import AuditLog, EmailVerificationToken
        from monitoring.models import Alert
        from ai_engine.models import AIAuditLog, AIClassificationLog

        if 'audit_logs' in ret:
            n, _ = AuditLog.objects.filter(created_at__lt=now - timedelta(days=ret['audit_logs'])).delete()
            deleted['audit_logs'] = n
        if 'alerts' in ret:
            n, _ = Alert.objects.filter(created_at__lt=now - timedelta(days=ret['alerts']), is_resolved=True).delete()
            deleted['alerts'] = n
        if 'verification_tokens' in ret:
            n, _ = EmailVerificationToken.objects.filter(
                created_at__lt=now - timedelta(days=ret['verification_tokens'])).delete()
            deleted['verification_tokens'] = n
        if 'ai_logs' in ret:
            cutoff = now - timedelta(days=ret['ai_logs'])
            n1, _ = AIAuditLog.objects.filter(created_at__lt=cutoff).delete()
            n2, _ = AIClassificationLog.objects.filter(created_at__lt=cutoff).delete()
            deleted['ai_logs'] = n1 + n2

        self.stdout.write(self.style.SUCCESS(f'Retention purge complete: {deleted}'))
