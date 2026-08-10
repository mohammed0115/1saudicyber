"""
Phase 3F — advisory analysis of one EvidenceSubmission (dry-run by default).

    python manage.py analyze_evidence_submission --submission-id 5 [--apply]

Advisory only: never creates ControlAssessment/CompanyControl, never accepts/rejects evidence.
"""
from django.core.management.base import BaseCommand, CommandError

from compliance.models import EvidenceSubmission
from compliance.evidence_analysis import analyze_evidence_submission


class Command(BaseCommand):
    help = 'Run advisory AI/OCR analysis on one evidence submission (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument('--submission-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Default; preview only.')

    def handle(self, *args, **options):
        sub = EvidenceSubmission.objects.filter(id=options['submission_id']).first()
        if not sub:
            raise CommandError(f"No EvidenceSubmission with id {options['submission_id']}.")
        apply = options['apply']
        res = analyze_evidence_submission(sub, apply=apply)
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(f'Evidence analysis ({mode}) — submission {sub.id}'))
        self.stdout.write(f"  result: {res}")
        if not apply:
            self.stdout.write(self.style.WARNING('  DRY-RUN: no database changes were made. Use --apply.'))
        self.stdout.write('  Advisory only — no ControlAssessment / accept / reject / report.')
