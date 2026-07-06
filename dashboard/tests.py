"""Dashboard app — role routing + each role dashboard renders (no 500) + tenant safety."""
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company


class DashboardRoutingTests(TestCase):
    def setUp(self):
        self.c = Company.objects.create(name='D', cr_number='1212121212', sector='technology',
                                        size='small', contact_email='d@x.com')

    def _cuser(self, role='compliance_officer', email=None):
        return User.objects.create_user(email=email or f'{role}@x.com', password='longenough12',
                                        role=role, company=self.c)

    def test_main_company_user_renders(self):
        self.client.force_login(self._cuser('compliance_officer'))
        self.assertEqual(self.client.get(reverse('dashboard:main')).status_code, 200)

    def test_main_staff_routed_to_platform_admin(self):
        u = User.objects.create_user(email='dstaff@x.com', password='longenough12',
                                     role='admin', is_staff=True)
        self.client.force_login(u)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/platform-admin/', resp.url)

    def test_main_auditor_routed_to_auditor_portal(self):
        from auditors.models import AuditorProfile
        u = User.objects.create_user(email='daud@x.com', password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=u, full_name='A', status='active')
        self.client.force_login(u)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auditor/', resp.url)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_unlinked_user_safe_no_company(self):
        u = User.objects.create_user(email='dorph@x.com', password='longenough12', role='compliance_officer')
        self.client.force_login(u)
        # company_portal_required serves a safe page; never 500
        self.assertNotEqual(self.client.get(reverse('dashboard:executive')).status_code, 500)


class DashboardRenderTests(TestCase):
    """Each role dashboard must render with NO data (no 500 / ZeroDivision / template break)."""
    def setUp(self):
        self.c = Company.objects.create(name='D2', cr_number='1313131313', sector='technology',
                                        size='small', contact_email='d2@x.com')
        self.u = User.objects.create_user(email='dash@x.com', password='longenough12',
                                          role='compliance_officer', company=self.c)
        self.client.force_login(self.u)

    def test_executive_dashboard_renders(self):
        self.assertEqual(self.client.get(reverse('dashboard:executive')).status_code, 200)

    def test_compliance_officer_dashboard_renders(self):
        self.assertEqual(self.client.get(reverse('dashboard:compliance_officer')).status_code, 200)

    def test_it_security_dashboard_renders(self):
        self.assertEqual(self.client.get(reverse('dashboard:it_security')).status_code, 200)

    def test_bu_manager_dashboard_renders(self):
        self.assertEqual(self.client.get(reverse('dashboard:bu_manager')).status_code, 200)
