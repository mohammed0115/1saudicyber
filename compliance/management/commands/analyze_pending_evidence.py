"""
Phase 3F — advisory analysis of pending evidence (dry-run by default).

    python manage.py analyze_pending_evidence --company-id 5 [--apply]

Company-scoped; advisory only.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.evidence_analysis import batch_analyze_pending_submissions


class Command(BaseCommand):
    help = 'Run advisory analysis on pending evidence submissions (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        company = None
        if options.get('company_id'):
            company = Company.objects.filter(id=options['company_id']).first()
            if not company:
                raise CommandError(f"No company with id {options['company_id']}.")
        apply = options['apply']
        res = batch_analyze_pending_submissions(company=company, apply=apply)
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Pending evidence analysis ({mode}) — {res["analyzed"]} submission(s)'))
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply.'))
        self.stdout.write('  Advisory only — no ControlAssessment / accept / reject / report.')
