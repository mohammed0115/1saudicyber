"""
G5 — scheduled reminder emails for pending audit work (run from cron, e.g. daily).

Reminds each company of: OPEN RFIs and OPEN findings that have been sitting for longer than
--days (default 3). Best-effort and idempotent-safe to re-run; it only reads state and sends
mail (no DB writes). In production wire it to cron:  manage.py send_audit_reminders --days 3
"""
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Email companies a reminder of their pending (open) RFIs and audit findings.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=3,
                            help='Only remind about items older than this many days (default 3).')

    def handle(self, *args, **options):
        from auditor_portal.models import DocumentRequest, AuditFinding
        from auditor_portal.notifications import _send, _company_emails
        cutoff = timezone.now() - timedelta(days=options['days'])

        pending = defaultdict(lambda: {'rfis': 0, 'findings': 0})
        for rfi in (DocumentRequest.objects.filter(status__in=DocumentRequest.OPEN_STATES,
                                                    created_at__lt=cutoff)
                    .select_related('company_control__company')):
            pending[rfi.company_control.company_id]['rfis'] += 1
        for f in (AuditFinding.objects.filter(status__in=AuditFinding.OPEN_STATES,
                                              created_at__lt=cutoff)
                  .select_related('company_control__company')):
            pending[f.company_control.company_id]['findings'] += 1

        if not pending:
            self.stdout.write('No pending items past the cutoff.')
            return

        from core.models import Company
        companies = {c.id: c for c in Company.objects.filter(id__in=pending.keys())}
        sent = 0
        for cid, counts in pending.items():
            company = companies.get(cid)
            if company is None:
                continue
            body = ('لديك عناصر تدقيق معلّقة بخصوص ملف «%s»:\n'
                    '- طلبات معلومات مفتوحة (RFI): %d\n'
                    '- ملاحظات تدقيق مفتوحة: %d\n\n'
                    'يرجى الدخول إلى المنصة لمتابعتها.'
                    % (company.name, counts['rfis'], counts['findings']))
            sent += _send(_company_emails(company), 'تذكير: عناصر تدقيق معلّقة', body)
        self.stdout.write('Reminders sent to %d recipient(s) across %d company(ies).'
                          % (sent, len(pending)))
