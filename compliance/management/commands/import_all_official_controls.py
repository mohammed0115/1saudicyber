"""R0 — import the FULL official control catalogue (all 7 frameworks) in one idempotent step.

    python manage.py import_all_official_controls            # dry-run (default, no writes)
    python manage.py import_all_official_controls --apply    # writes the full 417-control set

It first ensures the FrameworkVersion registry exists (seed_framework_versions), then imports
each official dataset via the audited import_official_controls command. Idempotent and
non-destructive: existing official controls are updated (not duplicated); CompanyControl,
Evidence and legacy rows are never touched.

Framework breakdown (matches the shipped YAML datasets):
    NCA ECC 2-2024 = 108, NCA CCC 2-2024 = 55, NCA CSCC = 32, NCA OSMACC = 15,
    NCA TCC = 21, Aramco SACS-002 = 92, SABIC CyberTrust = 94   ->   TOTAL = 417
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand

OFFICIAL_FRAMEWORK_VERSIONS = [
    'NCA-ECC-2-2024',
    'NCA-CCC-2-2024',
    'NCA-CSCC-1-2019',
    'NCA-TCC-1-2021',
    'NCA-OSMACC-1-2021',
    'ARAMCO-SACS-002',
    'SABIC-CYBERTRUST-1-0',
]
EXPECTED_TOTAL = 417


class Command(BaseCommand):
    help = 'Import the full official control catalogue (all 7 frameworks). Dry-run by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to the DB.')

    def handle(self, *args, **options):
        apply = options['apply']

        # 1) Ensure the Source Registry + FrameworkVersion records exist (idempotent).
        call_command('seed_framework_versions', stdout=StringIO(), stderr=StringIO())

        # 2) Import each official dataset (dry-run or apply).
        for code in OFFICIAL_FRAMEWORK_VERSIONS:
            call_command('import_official_controls', framework_version=code, apply=apply,
                         stdout=self.stdout, stderr=self.stderr)

        # 3) Report the resulting catalogue size.
        from compliance.models import Control
        total = Control.objects.filter(
            framework_version__code__in=OFFICIAL_FRAMEWORK_VERSIONS).count()
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(
            f'Official catalogue ({mode}): {total} controls across '
            f'{len(OFFICIAL_FRAMEWORK_VERSIONS)} frameworks.'))
        if apply and total != EXPECTED_TOTAL:
            self.stdout.write(self.style.WARNING(
                f'  Expected {EXPECTED_TOTAL} but found {total} — review dataset/import.'))
        elif not apply:
            self.stdout.write(self.style.WARNING(
                '  DRY-RUN: no database changes were made. Use --apply to write.'))
