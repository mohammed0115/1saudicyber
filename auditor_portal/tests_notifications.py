"""G5 — email notifications for audit events + the reminder command."""
from datetime import timedelta

from django.test import TestCase
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from compliance.models import Assessment, CompanyControl
from compliance.tests import _company_with_control, _assigned_auditor_user, _journey_user
from auditor_portal import findings_service as fs
from auditor_portal import notifications as notif
from auditor_portal.models import AuditFinding


class NotificationTests(TestCase):
    def _setup(self, email='notif@x.com'):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        cu = _journey_user(c, email=email.replace('@', '_co@'))   # a company user to receive mail
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = CompanyControl.objects.get_or_create(company=c, control=ctl)[0]
        return c, aud, cu, a, cc

    def test_new_finding_emails_company(self):
        c, aud, cu, a, cc = self._setup()
        mail.outbox = []
        f = fs.create_finding(a, cc, aud, severity='major_nc', title='t', description='d')
        notif.notify_new_finding(f)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(cu.email, mail.outbox[0].to)

    def test_add_finding_view_sends_email(self):
        c, aud, cu, a, cc = self._setup(email='notif2@x.com')
        mail.outbox = []
        self.client.post(reverse('auditor_portal:add_finding', args=[a.id, cc.id]),
                         {'severity': 'minor_nc', 'title': 't', 'description': 'd'})
        self.assertEqual(len(mail.outbox), 1)

    def test_message_notifies_other_participants_not_sender(self):
        c, aud, cu, a, cc = self._setup(email='notif3@x.com')
        mail.outbox = []
        self.client.post(reverse('auditor_portal:post_message', args=[c.id]), {'body': 'مرحبًا'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(cu.email, mail.outbox[0].to)
        self.assertNotIn(aud.email, mail.outbox[0].to)   # author not emailed

    def test_reminder_command_emails_pending(self):
        c, aud, cu, a, cc = self._setup(email='notif4@x.com')
        f = fs.create_finding(a, cc, aud, severity='major_nc', title='t', description='d')
        AuditFinding.objects.filter(id=f.id).update(created_at=timezone.now() - timedelta(days=10))
        mail.outbox = []
        call_command('send_audit_reminders', '--days', '3')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(cu.email, mail.outbox[0].to)

    def test_reminder_command_skips_recent(self):
        c, aud, cu, a, cc = self._setup(email='notif5@x.com')
        fs.create_finding(a, cc, aud, severity='minor_nc', title='t', description='d')  # created now
        mail.outbox = []
        call_command('send_audit_reminders', '--days', '3')
        self.assertEqual(len(mail.outbox), 0)   # too recent -> no reminder

    def test_finding_status_change_emails_company(self):
        c, aud, cu, a, cc = self._setup(email='notif6@x.com')
        f = fs.create_finding(a, cc, aud, severity='major_nc', title='t', description='d')
        mail.outbox = []
        self.client.post(reverse('auditor_portal:update_finding_status', args=[f.id]),
                         {'status': 'in_remediation'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(cu.email, mail.outbox[0].to)

    def test_company_capa_emails_auditor(self):
        c, aud, cu, a, cc = self._setup(email='notif7@x.com')
        f = fs.create_finding(a, cc, aud, severity='minor_nc', title='t', description='d')
        self.client.force_login(cu)
        mail.outbox = []
        self.client.post(reverse('auditor_portal:company_add_corrective_action', args=[f.id]),
                         {'description': 'سننفّذ'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(aud.email, mail.outbox[0].to)
