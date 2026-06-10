"""
Phase 3D — generate company-specific evidence checklist plans (dry-run by default).

    python manage.py generate_evidence_checklist --company-id 5 [--framework-version CODE] [--apply]

Plans EvidenceChecklistItem for applicable OFFICIAL controls only. Never creates
Evidence / CompanyControl / EvidenceSubmission; never changes the upload flow.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.models import CompanyFrameworkScope
from compliance.evidence_planning import (
    generate_evidence_checklist_for_company, generate_evidence_checklist_for_framework_scope,
)


class Command(BaseCommand):
    help = 'Generate company evidence checklist plan from applicable official controls (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--framework-version', help='Limit to one approved framework version code.')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        apply = options['apply']
        company = Company.objects.filter(id=options['company_id']).first()
        if not company:
            raise CommandError(f"No company with id {options['company_id']}.")
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Evidence checklist ({mode}) — {company.name}'))

        if options.get('framework_version'):
            scope = CompanyFrameworkScope.objects.filter(
                company=company, framework_version__code=options['framework_version']).first()
            if not scope:
                raise CommandError(f"No framework scope {options['framework_version']} for this company.")
            res = generate_evidence_checklist_for_framework_scope(scope, apply=apply)
            self.stdout.write(f"  {options['framework_version']}: {res}")
        else:
            res = generate_evidence_checklist_for_company(company, apply=apply)
            self.stdout.write(f"  planned checklist items: {res['planned']}")
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply.'))
        self.stdout.write('  Evidence / CompanyControl / upload: untouched.')
