"""
Phase 3G — create not_reviewed ControlAssessment rows for applicable official controls (dry-run default).

    python manage.py generate_control_assessments --company-id 5 [--apply]

Official controls only. Never creates CompanyControl, never generates reports,
never sets a final compliance status (auditor does that in the UI).
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.control_assessment import create_assessments_for_company


class Command(BaseCommand):
    help = 'Create not_reviewed control assessments for applicable official controls (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        company = Company.objects.filter(id=options['company_id']).first()
        if not company:
            raise CommandError(f"No company with id {options['company_id']}.")
        apply = options['apply']
        stats = create_assessments_for_company(company, apply=apply)
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Control assessments ({mode}) — {company.name}'))
        self.stdout.write(f"  {'created' if apply else 'would_create'}: {stats['created']}")
        if apply:
            self.stdout.write(f"  already existing: {stats['existing']}")
        else:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply.'))
        self.stdout.write('  Official only — no CompanyControl, no reports, no AI decision.')
