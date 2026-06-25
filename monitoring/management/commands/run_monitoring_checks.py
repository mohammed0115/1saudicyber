"""Phase 5B — run due continuous-monitoring checks. Dry-run by default."""
from django.core.management.base import BaseCommand

from monitoring.continuous import run_due_monitoring_checks


class Command(BaseCommand):
    help = ('Run due continuous-monitoring checks. Dry-run by default (writes nothing); '
            'use --apply to create runs/findings and reschedule checks.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Persist runs/findings.')
        parser.add_argument('--dry-run', action='store_true', help='Explicit dry-run (default).')
        parser.add_argument('--company-id', type=int, default=None)
        parser.add_argument('--check-type', type=str, default=None)
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **opts):
        apply = opts['apply'] and not opts['dry_run']
        company = None
        if opts['company_id']:
            from core.models import Company
            company = Company.objects.filter(id=opts['company_id']).first()
            if company is None:
                self.stdout.write(self.style.WARNING(f"No company id={opts['company_id']}; scanning all."))

        result = run_due_monitoring_checks(
            apply=apply, company=company, check_type=opts['check_type'], limit=opts['limit'])

        mode = 'APPLY' if apply else 'DRY-RUN (no records written)'
        self.stdout.write(mode)
        self.stdout.write(f"  checks scanned : {result['scanned']}")
        self.stdout.write(f"  checks due     : {result['due']}")
        self.stdout.write(f"  runs created   : {result['runs_created']}")
        self.stdout.write(f"  findings created: {result['findings_created']}")
        self.stdout.write(f"  errors         : {result['errors']}")
        if not apply:
            self.stdout.write("Run again with --apply to persist runs/findings.")
        else:
            self.stdout.write(self.style.SUCCESS("Monitoring run complete."))
