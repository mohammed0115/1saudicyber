"""DEF-03: Django-admin control search reaches CCC / cloud controls (search_fields fix)."""
from django.test import TestCase

from core.models import User
from compliance.models import Framework, FrameworkVersion, Domain, Control


class ControlAdminSearchTests(TestCase):
    def setUp(self):
        fw = Framework.objects.get_or_create(code='NCA_CCC', defaults={'name': 'NCA CCC'})[0]
        self.fv = FrameworkVersion.objects.get_or_create(
            code='NCA-CCC-2-2024', defaults={'framework': fw, 'version_label': 'CCC 2:2024'})[0]
        dom = Domain.objects.get_or_create(framework=fw, name='Cloud Computing', defaults={'code': 'CC'})[0]
        self.control = Control.objects.create(
            framework=fw, framework_version=self.fv, control_id='1-1-P-1',
            title='Cloud computing cybersecurity requirement', description='x', domain=dom)
        self.client.force_login(
            User.objects.create_superuser(email='root@x.com', password='longenough12'))

    def _search(self, q):
        return self.client.get('/admin/compliance/control/', {'q': q}).content.decode()

    def test_search_by_framework_code_ccc(self):
        self.assertIn('1-1-P-1', self._search('CCC'))        # framework_version__code

    def test_search_by_title_cloud(self):
        self.assertIn('1-1-P-1', self._search('cloud'))      # title

    def test_search_by_domain_name(self):
        self.assertIn('1-1-P-1', self._search('Cloud Computing'))  # domain__name
