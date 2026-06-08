"""
Run the continuous-monitoring pipeline synchronously (no Celery/Redis needed).
Use from cron or manually:  python manage.py run_monitoring [--monthly]
"""
from django.core.management.base import BaseCommand
from core.models import Company
from monitoring.services import run_company_checks, generate_monthly_report


class Command(BaseCommand):
    help = 'Recalculate scores, raise alerts, and (optionally) generate monthly reports.'

    def add_arguments(self, parser):
        parser.add_argument('--monthly', action='store_true', help='Also generate monthly reports.')

    def handle(self, *args, **options):
        companies = Company.objects.all()
        for c in companies:
            res = run_company_checks(c)
            if options['monthly']:
                generate_monthly_report(c)
            self.stdout.write(f'  {c.name}: {res}')
        self.stdout.write(self.style.SUCCESS(f'Monitoring complete for {companies.count()} companies.'))
