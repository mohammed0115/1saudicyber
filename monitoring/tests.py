"""
Regression test for PATCH_NOTES fix #4 (Prototype Phase 10B):
the realtime_monitoring view referenced templates/monitoring/realtime.html,
which previously did not exist -> TemplateDoesNotExist crash.
"""
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company


class RealtimeTemplateTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Co', cr_number='1313131313', sector='technology', size='small',
            contact_email='c@x.com', target_nca=True)
        self.user = User.objects.create_user(
            email='rt@x.com', password='longenough12', company=self.company, role='company_admin')
        self.client.force_login(self.user)

    def test_realtime_page_renders(self):
        resp = self.client.get(reverse('monitoring:realtime'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'monitoring/realtime.html')
