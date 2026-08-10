"""G5 — per-company internal message thread: access control + posting."""
from django.test import TestCase
from django.urls import reverse

from core.models import Company
from compliance.tests import _company_with_control, _assigned_auditor_user, _journey_user
from auditor_portal.models import CompanyMessage


def _other_company(cr='5566778899'):
    return Company.objects.create(name='Other', cr_number=cr, sector='technology',
                                  size='small', contact_email='oth@x.com')


class MessageThreadAccessTests(TestCase):
    def _url(self, company, post=False):
        name = 'auditor_portal:post_message' if post else 'auditor_portal:message_thread'
        return reverse(name, args=[company.id])

    def test_company_user_can_view_and_post(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='msg_co@x.com'))
        self.assertEqual(self.client.get(self._url(c)).status_code, 200)
        self.client.post(self._url(c, post=True), {'body': 'مرحبًا، لدينا سؤال.'})
        self.assertEqual(CompanyMessage.objects.filter(company=c).count(), 1)

    def test_assigned_auditor_can_view_and_post(self):
        c, _ = _company_with_control()
        aud = _assigned_auditor_user(c, email='msg_aud@x.com')   # accepted assignment to c
        self.client.force_login(aud)
        self.assertEqual(self.client.get(self._url(c)).status_code, 200)
        self.client.post(self._url(c, post=True), {'body': 'يرجى رفع سياسة الوصول.'})
        m = CompanyMessage.objects.get(company=c)
        self.assertEqual(m.sender, aud)

    def test_staff_can_view(self):
        from core.models import User
        c, _ = _company_with_control()
        staff = User.objects.create_user(email='msg_staff@x.com', username='msg_staff@x.com',
                                         password='longenough12', role='admin', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self._url(c)).status_code, 200)

    def test_other_company_user_blocked(self):
        c, _ = _company_with_control()
        c2 = _other_company()
        self.client.force_login(_journey_user(c2, email='msg_x@x.com'))
        self.assertEqual(self.client.get(self._url(c)).status_code, 404)
        self.assertEqual(self.client.post(self._url(c, post=True), {'body': 'x'}).status_code, 404)
        self.assertEqual(CompanyMessage.objects.filter(company=c).count(), 0)

    def test_unassigned_auditor_blocked(self):
        c, _ = _company_with_control()
        c2 = _other_company(cr='1112223334')
        aud2 = _assigned_auditor_user(c2, email='msg_aud2@x.com')   # assigned to c2, NOT c
        self.client.force_login(aud2)
        self.assertEqual(self.client.get(self._url(c)).status_code, 404)

    def test_post_get_is_405(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='msg_405@x.com'))
        self.assertEqual(self.client.get(self._url(c, post=True)).status_code, 405)
