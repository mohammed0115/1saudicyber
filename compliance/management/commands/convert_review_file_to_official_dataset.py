"""
Phase 2P — convert a human-review file into an official dataset YAML (conservatively).

    python manage.py convert_review_file_to_official_dataset --framework-version NCA-OTCC-1-2022 --dry-run
    python manage.py convert_review_file_to_official_dataset --framework-version NCA-OTCC-1-2022 --write-dataset

Reads compliance/data/official_controls/manual_review/<fv>_review.json, validates EVERY row,
and only writes the official YAML when ALL rows are approved & clean. Dry-run by default.
It does NOT register the dataset in DATASET_FILES, does NOT import controls, and never
touches CompanyControl / Evidence / EvidenceRequirement / upload / registration.
"""
import json
import re
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

REVIEW_DIR = Path(__file__).resolve().parents[2] / 'data' / 'official_controls' / 'manual_review'
OUT_DIR = Path(__file__).resolve().parents[2] / 'data' / 'official_controls'

# fv code -> (review filename, output filename, expected count, id pattern, doc title)
SPECS = {
    'NCA-OTCC-1-2022': ('nca_otcc_1_2022_review.json', 'nca_otcc_1_2022.yaml', 47,
                        r'^\d+-\d+-\d+$', 'NCA Operational Technology Cybersecurity Controls'),
}
REQUIRED = ('control_id', 'external_reference', 'domain', 'subdomain', 'title', 'statement', 'source_reference')
SUBCONTROL_RE = re.compile(r'^\d+-\d+-\d+-\d+$')


class Command(BaseCommand):
    help = 'Convert a reviewed control file to official YAML (dry-run by default; all rows must be approved).'

    def add_arguments(self, parser):
        parser.add_argument('--framework-version', required=True)
        parser.add_argument('--write-dataset', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; validate only.')
        parser.add_argument('--review-file', help='Override the review file path.')

    def handle(self, *args, **options):
        fv = options['framework_version']

        # DCC (and any unspecced fv) is guarded explicitly.
        if fv not in SPECS:
            review = options.get('review_file') or str(REVIEW_DIR / f"{fv.lower().replace('-', '_')}_review.json")
            self._dcc_or_blocked_guard(fv, review)
            raise CommandError(
                f"{fv} cannot be converted to official YAML until a text-based official source or "
                f"OCR-reviewed control list is available.")

        fname, out_name, expected, id_pat, title = SPECS[fv]
        path = Path(options['review_file']) if options.get('review_file') else REVIEW_DIR / fname
        if not path.exists():
            raise CommandError(f"Review file not found: {path}")
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            raise CommandError(f"{path} must be a JSON list of control rows.")

        errors = []
        if len(rows) != expected:
            errors.append(f"expected exactly {expected} rows, found {len(rows)}.")
        seen = set()
        for i, r in enumerate(rows):
            cid = r.get('control_id', f'<row {i}>')
            if r.get('review_status') != 'approved_for_dataset':
                errors.append(f"{cid}: review_status='{r.get('review_status')}' (must be approved_for_dataset).")
            for f in REQUIRED:
                if not str(r.get(f, '')).strip():
                    errors.append(f"{cid}: missing '{f}'.")
            if r.get('control_id') and not re.match(id_pat, r['control_id']):
                errors.append(f"{cid}: control_id does not match {id_pat}.")
            if r.get('control_id') and SUBCONTROL_RE.match(r['control_id']):
                errors.append(f"{cid}: subcontrol id (x-x-x-x) not allowed.")
            if r.get('control_id') in seen:
                errors.append(f"{cid}: duplicate control_id.")
            seen.add(r.get('control_id'))

        self.stdout.write(f'Review-to-YAML conversion — {fv}')
        self.stdout.write(f'  review file: {path}')
        self.stdout.write(f'  rows: {len(rows)} | expected: {expected}')
        if errors:
            for e in errors[:50]:
                self.stdout.write(self.style.ERROR(f'  ERROR: {e}'))
            raise CommandError(f'Conversion blocked: {len(errors)} validation error(s). No YAML written.')

        self.stdout.write(self.style.SUCCESS('  All rows approved and valid.'))
        if not options['write_dataset']:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no YAML written. Use --write-dataset to write.'))
            return

        doc = {
            'framework_version_code': fv, 'source_document_title': title,
            'expected_control_count': len(rows),
            'notes': 'Generated from human-reviewed manual_review file (Phase 2P). NOT auto-registered.',
            'controls': [{
                'control_id': r['control_id'], 'external_reference': r['external_reference'],
                'domain': r['domain'], 'subdomain': r['subdomain'], 'title': r['title'],
                'statement': r['statement'], 'level': r.get('level', 'control'),
                'source_reference': r['source_reference'], 'source_page': r.get('source_page'),
                'tags': r.get('tags', []),
            } for r in rows],
        }

        class LD(yaml.SafeDumper):
            pass
        LD.add_representer(str, lambda d, data: d.represent_scalar(
            'tag:yaml.org,2002:str', data, style=('>' if len(data) > 80 else None)))
        out = OUT_DIR / out_name
        with open(out, 'w', encoding='utf-8') as f:
            f.write('# CyberTrust KSA — Official dataset generated from human review (Phase 2P).\n')
            f.write('# NOT registered in DATASET_FILES until explicitly requested.\n')
            yaml.dump(doc, f, Dumper=LD, allow_unicode=True, sort_keys=False, width=100)
        self.stdout.write(self.style.SUCCESS(f'  Wrote {out} ({len(rows)} controls). Not auto-registered.'))

    def _dcc_or_blocked_guard(self, fv, review_path):
        """Print a clear blocker summary for DCC / any unspecced framework."""
        p = Path(review_path)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                self.stdout.write(f"  {fv} review status: {data.get('review_status')}")
                self.stdout.write(f"  blocker: {data.get('blocker_reason', 'n/a')}")
            except Exception:
                pass
