"""
Phase 2F — validate an official control dataset (READ-ONLY, never writes DB).

    python manage.py validate_official_control_dataset --framework-version ARAMCO-SACS-002

Exits non-zero when any error is found (CI-friendly).
"""
import re

from django.core.management.base import BaseCommand, CommandError

from compliance.models import FrameworkVersion
from compliance.official_dataset import load_official_dataset, ID_PATTERNS, DatasetError

REQUIRED_FIELDS = ('control_id', 'external_reference', 'domain', 'title', 'statement')


class Command(BaseCommand):
    help = 'Validate an official control dataset YAML (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--framework-version', required=True)

    def handle(self, *args, **options):
        fv_code = options['framework_version']
        errors, warnings = [], []

        try:
            metadata, controls = load_official_dataset(fv_code)
        except DatasetError as exc:
            raise CommandError(str(exc))

        # File declares the same framework_version it was requested for.
        file_code = metadata.get('framework_version_code')
        if file_code != fv_code:
            errors.append(f"framework_version_code in file ('{file_code}') != requested ('{fv_code}').")

        # FrameworkVersion + SourceDocument must exist in the DB.
        fv = FrameworkVersion.objects.filter(code=fv_code).first()
        if fv is None:
            errors.append(f"FrameworkVersion '{fv_code}' not found in DB. Run seed_framework_versions.")
        elif fv.source_document is None:
            errors.append(f"FrameworkVersion '{fv_code}' has no source_document.")

        # No reliance on the legacy 334 Excel as an authority.
        blob = ' '.join(str(metadata.get(k, '')) for k in ('source_document_title', 'notes')).lower()
        if 'legacy' in blob and 'not derived' not in blob and 'not from' not in blob:
            warnings.append("metadata mentions 'legacy' — confirm the Excel 334 is not used as a source.")

        id_pattern = ID_PATTERNS.get(fv_code)
        seen = set()
        for i, c in enumerate(controls):
            cid = c.get('control_id', f'<row {i}>')
            for fld in REQUIRED_FIELDS:
                if not str(c.get(fld, '')).strip():
                    errors.append(f"{cid}: missing required field '{fld}'.")
            if not str(c.get('source_reference', '')).strip() and not c.get('source_page'):
                errors.append(f"{cid}: needs source_reference or source_page.")
            if id_pattern and c.get('control_id') and not re.match(id_pattern, c['control_id']):
                errors.append(f"{cid}: control_id does not match pattern {id_pattern}.")
            if c.get('control_id') in seen:
                errors.append(f"{cid}: duplicate control_id within this framework_version.")
            seen.add(c.get('control_id'))

        expected = metadata.get('expected_control_count')
        actual = len(controls)
        if expected is not None and expected != actual:
            errors.append(f"expected_control_count={expected} but found {actual} controls.")

        # ---- summary ----
        self.stdout.write('Official control dataset validation')
        self.stdout.write(f"  file:              {metadata.get('_path')}")
        self.stdout.write(f"  framework_version: {fv_code}")
        self.stdout.write(f"  expected count:    {expected}")
        self.stdout.write(f"  actual count:      {actual}")
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  WARNING: {w}"))
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  ERROR: {e}"))
            raise CommandError(f"Validation FAILED with {len(errors)} error(s).")
        self.stdout.write(self.style.SUCCESS(f"  OK — {actual} controls valid, 0 errors."))
