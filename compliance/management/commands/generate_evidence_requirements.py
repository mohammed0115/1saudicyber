"""
Phase 3D — create default EvidenceRequirement templates for official controls (dry-run by default).

    python manage.py generate_evidence_requirements [--framework-version NCA-ECC-2-2024] [--apply]

Official controls only. Never creates Evidence / CompanyControl / EvidenceChecklistItem.
"""
from django.core.management.base import BaseCommand

from compliance.evidence_planning import generate_evidence_requirements


class Command(BaseCommand):
    help = 'Create default evidence requirement templates for official controls (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--framework-version')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        apply = options['apply']
        stats = generate_evidence_requirements(apply=apply, framework_version_code=options.get('framework_version'))
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Evidence requirements ({mode})'))
        self.stdout.write(f"  official controls scanned: {stats['official_controls']}")
        self.stdout.write(f"  {'created' if apply else 'would_create'}: {stats['created']}")
        if apply:
            self.stdout.write(f"  already existing: {stats['existing']}")
        else:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply.'))
        self.stdout.write('  Evidence / CompanyControl / upload: untouched.')
