"""
Phase 2A — bridge existing (legacy) controls to a FrameworkVersion.

This is a TEMPORARY bridge, NOT the official source linkage (that comes with the
Phase 2B official import). It only fills `Control.framework_version` for controls
that don't have one yet, choosing the default active version of the control's
existing `framework`. It marks each linked control as a legacy import.

Safety:
  * idempotent — only links controls whose framework_version is still NULL.
  * never creates or deletes Control rows.
  * never touches CompanyControl or Evidence.
  * never fails when a mapping can't be made — it skips and reports.

Usage:
    python manage.py link_legacy_controls_to_framework_versions
"""
from django.core.management.base import BaseCommand

from compliance.models import Control, Framework, FrameworkVersion

BRIDGE_NOTE = 'Linked from existing legacy control import; official source verification pending.'


class Command(BaseCommand):
    help = 'Phase 2A: bridge existing controls to a default FrameworkVersion (idempotent, non-destructive).'

    def handle(self, *args, **options):
        # Cache the default active version per framework id.
        default_version = {}
        for fw in Framework.objects.all():
            ver = (FrameworkVersion.objects.filter(framework=fw, is_default=True).first()
                   or FrameworkVersion.objects.filter(framework=fw, status='active').first())
            if ver:
                default_version[fw.id] = ver

        total = Control.objects.count()
        linked = skipped = 0
        missing_versions = set()

        for control in Control.objects.select_related('framework').all():
            if control.framework_version_id is not None:
                skipped += 1  # already linked -> idempotent no-op
                continue
            ver = default_version.get(control.framework_id)
            if ver is None:
                missing_versions.add(control.framework.code if control.framework else '(none)')
                skipped += 1
                continue
            control.framework_version = ver
            control.is_legacy_import = True
            if not control.import_notes:
                control.import_notes = BRIDGE_NOTE
            control.save(update_fields=['framework_version', 'is_legacy_import', 'import_notes'])
            linked += 1

        self.stdout.write(self.style.SUCCESS('Legacy control linking complete (temporary bridge).'))
        self.stdout.write(f'  total controls: {total}')
        self.stdout.write(f'  linked controls: {linked}')
        self.stdout.write(f'  skipped controls: {skipped}')
        self.stdout.write(f'  frameworks missing a version: {sorted(missing_versions) or "none"}')
