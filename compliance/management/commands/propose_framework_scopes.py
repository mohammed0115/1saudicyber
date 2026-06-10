"""
Phase 3C — propose framework scopes from applicability results (dry-run by default).

    python manage.py propose_framework_scopes --company-id 5
    python manage.py propose_framework_scopes --all-companies --apply

Never creates CompanyControl / Evidence / EvidenceRequirement.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.framework_scope import propose_framework_scopes


class Command(BaseCommand):
    help = 'Propose CompanyFrameworkScope rows from applicability results (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int)
        parser.add_argument('--all-companies', action='store_true')
        parser.add_argument('--apply', action='store_true')
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
        self.stdout.write(self.style.SUCCESS(f'Propose framework scopes ({mode}) — {len(companies)} company(ies)'))
        proposed = skipped = 0
        for company in companies:
            self.stdout.write(f'\n[{company.id}] {company.name}')
            for r in propose_framework_scopes(company, apply=apply):
                self.stdout.write(f"    - {r['framework']}: {r['status']} — {r['reason']}")
                if r['status'] == 'skipped':
                    skipped += 1
                else:
                    proposed += 1
        self.stdout.write(f"\n  proposed/needs_review scopes: {proposed} | skipped: {skipped}")
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply to write.'))
        self.stdout.write('  CompanyControl / Evidence / EvidenceRequirement: untouched.')
