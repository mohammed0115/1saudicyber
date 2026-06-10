"""
Phase 2F — import official controls from a validated dataset.

    python manage.py import_official_controls --framework-version ARAMCO-SACS-002 --dry-run   # default
    python manage.py import_official_controls --framework-version ARAMCO-SACS-002 --apply

Behaviour:
  * dry-run is the DEFAULT; nothing is written unless --apply is given.
  * runs the dataset validation first and aborts on errors.
  * identity = (framework_version, control_id); legacy rows (fv NULL) are never touched.
  * never touches CompanyControl or Evidence; never deletes anything.
  * idempotent: existing official controls (incl. the 2B pilot TPC-1..3) are UPDATED, not duplicated.
  * writes/refreshes a ControlVersion snapshot per control on --apply.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from compliance.models import FrameworkVersion, Domain, Control, ControlVersion
from compliance.official_dataset import load_official_dataset, DatasetError

IMPORT_NOTE = 'Official import from curated dataset (Phase 2F). Source: official standard, not legacy Excel.'

# Fields that determine whether an existing official control is "unchanged".
COMPARE = ('title', 'description', 'source_reference', 'external_reference', 'source_page')


class Command(BaseCommand):
    help = 'Import official controls from a curated dataset (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--framework-version', required=True)
        parser.add_argument('--apply', action='store_true', help='Actually write to the DB.')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        fv_code = options['framework_version']
        apply = options['apply']  # dry-run unless --apply

        # 1) validate first (raises CommandError on failure).
        call_command('validate_official_control_dataset', framework_version=fv_code,
                     stdout=self.stdout, stderr=self.stderr)

        try:
            _, controls = load_official_dataset(fv_code)
        except DatasetError as exc:
            raise CommandError(str(exc))

        fv = FrameworkVersion.objects.filter(code=fv_code).first()
        if fv is None:
            raise CommandError(f"FrameworkVersion '{fv_code}' not found.")
        fw, src = fv.framework, fv.source_document

        would_create = would_update = unchanged = 0
        warnings = []

        def field_set(c):
            return dict(
                framework=fw, title=c['title'], description=c['statement'],
                source_document=src, source_page=c.get('source_page'),
                source_reference=c.get('source_reference', ''),
                external_reference=c.get('external_reference', ''),
                is_legacy_import=False, import_notes=IMPORT_NOTE, priority='high')

        def classify(existing, desired):
            if existing is None:
                return 'create'
            for f in COMPARE:
                if getattr(existing, f) != desired.get(f if f != 'description' else 'description'):
                    return 'update'
            return 'unchanged'

        @transaction.atomic
        def run(write):
            nonlocal would_create, would_update, unchanged
            sid = transaction.savepoint()
            for c in controls:
                existing = Control.objects.filter(framework_version=fv, control_id=c['control_id']).first()
                desired = field_set(c)
                verdict = classify(existing, desired)
                if verdict == 'create':
                    would_create += 1
                elif verdict == 'update':
                    would_update += 1
                else:
                    unchanged += 1
                if not write:
                    continue
                domain, _ = Domain.objects.get_or_create(
                    framework=fw, code=c.get('domain', 'GEN'),
                    defaults={'name': c.get('domain', 'General')})
                control, _ = Control.objects.update_or_create(
                    framework_version=fv, control_id=c['control_id'],
                    defaults={**desired, 'domain': domain})
                ControlVersion.objects.update_or_create(
                    control=control, framework_version=fv,
                    version_label=fv.version_label or fv.code,
                    defaults=dict(source_document=src, control_id_snapshot=c['control_id'],
                                  title_snapshot=c['title'], statement_snapshot=c['statement'],
                                  change_summary='Official dataset import (Phase 2F).'))
            if not write:
                transaction.savepoint_rollback(sid)  # extra safety for dry-run
            else:
                transaction.savepoint_commit(sid)

        run(write=apply)

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f"Official import ({mode}) — {fv_code}"))
        self.stdout.write(f"  would_create: {would_create}" if not apply else f"  created: {would_create}")
        self.stdout.write(f"  would_update: {would_update}" if not apply else f"  updated: {would_update}")
        self.stdout.write(f"  unchanged:    {unchanged}")
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  WARNING: {w}"))
        self.stdout.write("  legacy / CompanyControl / Evidence: untouched")
        if not apply:
            self.stdout.write(self.style.WARNING("  DRY-RUN: no database changes were made. Use --apply to write."))
