"""
Phase 3C — generate the control applicability plan for approved framework scopes
(dry-run by default).

    python manage.py generate_control_applicability_plan --company-id 5 --framework-version NCA-ECC-2-2024
    python manage.py generate_control_applicability_plan --company-id 5 --all-approved --apply

Plans OFFICIAL controls only. Never creates CompanyControl / Evidence / EvidenceRequirement.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from compliance.models import CompanyFrameworkScope
from compliance.framework_scope import generate_control_applicability_plan


class Command(BaseCommand):
    help = 'Generate ControlApplicabilityResult plan for approved framework scopes (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--framework-version', help='FrameworkVersion code.')
        parser.add_argument('--all-approved', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        apply = options['apply']
        company = Company.objects.filter(id=options['company_id']).first()
        if not company:
            raise CommandError(f"No company with id {options['company_id']}.")

        scopes = CompanyFrameworkScope.objects.filter(company=company, status='approved')
        if options['framework_version']:
            scopes = scopes.filter(framework_version__code=options['framework_version'])
        elif not options['all_approved']:
            raise CommandError('Provide --framework-version <code> or --all-approved.')

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(
            f'Control applicability plan ({mode}) — {company.name} — {scopes.count()} approved scope(s)'))
        total = 0
        for scope in scopes:
            count, _ = generate_control_applicability_plan(company, scope, apply=apply)
            total += count
            self.stdout.write(f"    - {scope.framework_version.code}: {count} official control(s) planned")
        self.stdout.write(f"\n  planned controls: {total}")
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply to write.'))
        self.stdout.write('  CompanyControl / Evidence / EvidenceRequirement: untouched.')
