"""Reprocess Evidence rows stuck in a non-terminal status, synchronously.

    python manage.py process_pending_evidence [--company-id N] [--limit N]

Finds Evidence whose status is still 'processing' or 'ai_analyzing' (e.g. left behind by a
crashed/absent Celery worker) and runs the SAME OCR + AI pipeline synchronously — no broker
or worker required. Each row is driven to a terminal status. Safe to re-run.

NB: this operates on the `Evidence` model (control-detail upload path). The advisory
`analyze_pending_evidence` command is a DIFFERENT thing — it works on EvidenceSubmission.
"""
from django.core.management.base import BaseCommand

from compliance.models import Evidence
from compliance.services import process_evidence_pipeline

STUCK_STATUSES = ['processing', 'ai_analyzing']


class Command(BaseCommand):
    help = 'Synchronously process Evidence rows stuck in processing/ai_analyzing.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, help='Limit to one company.')
        parser.add_argument('--limit', type=int, default=0, help='Max rows to process (0 = all).')

    def handle(self, *args, **options):
        qs = Evidence.objects.filter(status__in=STUCK_STATUSES).order_by('id')
        if options.get('company_id'):
            qs = qs.filter(company_control__company_id=options['company_id'])
        if options.get('limit'):
            qs = qs[:options['limit']]

        ids = list(qs.values_list('id', flat=True))
        if not ids:
            self.stdout.write(self.style.SUCCESS('No stuck evidence found.'))
            return

        self.stdout.write(f'Processing {len(ids)} stuck evidence row(s) ...')
        done, errored = 0, 0
        for eid in ids:
            result = process_evidence_pipeline(eid)
            if result.get('error'):
                errored += 1
                self.stdout.write(self.style.WARNING(f'  evidence {eid}: {result["error"]}'))
            else:
                done += 1
                self.stdout.write(f'  evidence {eid}: {result.get("verdict", "done")}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. {done} processed, {errored} errored. None left as processing.'))
