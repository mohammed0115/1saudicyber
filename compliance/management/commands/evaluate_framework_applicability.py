"""
Phase 3A — evaluate framework applicability for one or all companies.

    python manage.py evaluate_framework_applicability --company-id 5            # dry-run (default)
    python manage.py evaluate_framework_applicability --all-companies --apply

Dry-run by default: prints decisions, writes nothing. --apply persists
FrameworkApplicabilityResult rows (idempotent). Never creates CompanyControl or
Evidence; never touches the upload flow.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.framework_applicability import evaluate_company


class Command(BaseCommand):
    help = 'Evaluate deterministic framework applicability (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--all-companies', action='store_true')
        parser.add_argument('--apply', action='store_true', help='Persist results (else dry-run).')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        apply = options['apply']
        if options['all_companies']:
            companies = list(Company.objects.all())
        elif options['company_id']:
            companies = list(Company.objects.filter(id=options['company_id']))
            if not companies:
                raise CommandError(f"No company with id {options['company_id']}.")
        else:
            raise CommandError('Provide --company-id <id> or --all-companies.')

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Framework applicability ({mode}) — {len(companies)} company(ies)'))
        written = 0
        for company in companies:
            self.stdout.write(f'\n[{company.id}] {company.name}')
            for r in evaluate_company(company, apply=apply):
                if r['status'] in ('unavailable', 'skipped'):
                    self.stdout.write(f"    - {r['framework']}: {r['status']} ({r['reason']})")
                else:
                    src = r.get('source', '')
                    self.stdout.write(f"    - {r['framework']}: {r['status']} [{src}] — {r['reason']}")
                    if apply and r['status'] != 'manually_overridden':
                        written += 1
        if not apply:
            self.stdout.write(self.style.WARNING('\nDRY-RUN: no database changes were made. Use --apply to write.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nWrote/updated {written} applicability result(s).'))
        self.stdout.write('CompanyControl / Evidence / upload flow: untouched.')
