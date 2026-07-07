"""R2 — populate conservative condition tags on controls (ControlApplicabilityTag).

Tags are derived from the OFFICIAL structure only:
  * whole condition-specific frameworks (CCC=cloud, CSCC=critical_system, TCC=remote_work,
    OSMACC=social_media, OTCC=ot_ics); and
  * precise control-TITLE keywords (e.g. ECC 4-2-x "cloud computing and hosting" -> cloud).

Only conditions backed by a single, reliable CompanyIntakeProfile signal are tagged, so
applicability can be NARROWED safely — never under-scoped. General third-party / personal-data
controls are deliberately NOT tagged (no reliable single signal). Idempotent; dry-run default.
"""
from django.core.management.base import BaseCommand

from compliance.models import Control, ControlApplicabilityTag

# Whole condition-specific frameworks -> their condition tag.
FRAMEWORK_TAG = {
    'NCA-CCC-2-2024': 'cloud',
    'NCA-CSCC-1-2019': 'critical_system',
    'NCA-TCC-1-2021': 'remote_work',
    'NCA-OSMACC-1-2021': 'social_media',
    'NCA-OTCC-1-2022': 'ot_ics',
}

# Precise control-title keywords -> tag (applied within any framework, e.g. ECC's cloud controls).
TITLE_KEYWORD_TAG = [
    (('cloud computing', 'cloud hosting', 'cloud and hosting', 'hosting services', 'سحاب'), 'cloud'),
    (('operational technology', 'industrial control', 'scada', 'التقنية التشغيلية'), 'ot_ics'),
]


class Command(BaseCommand):
    help = 'Populate conservative condition tags on controls (idempotent). Dry-run by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write tags.')

    def handle(self, *args, **options):
        apply = options['apply']
        added = 0
        for control in Control.objects.select_related('framework_version').all():
            tags = set()
            fv = control.framework_version
            if fv is not None and fv.code in FRAMEWORK_TAG:
                tags.add(FRAMEWORK_TAG[fv.code])
            title = (control.title or '').lower()
            for keywords, tag in TITLE_KEYWORD_TAG:
                if any(k in title for k in keywords):
                    tags.add(tag)
            for tag in tags:
                exists = control.applicability_tags.filter(tag=tag).exists()
                if not exists:
                    added += 1
                    if apply:
                        ControlApplicabilityTag.objects.get_or_create(
                            control=control, tag=tag, defaults={'source': 'inferred'})

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Conditional tags ({mode}): {added} new tag(s).'))
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: use --apply to write.'))
