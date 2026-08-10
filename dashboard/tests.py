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


class CompanyDashboardScopeStateTests(TestCase):
    """UAT: the company dashboard is driven by approved scope + generated control plan only."""

    def setUp(self):
        from compliance.models import Framework, FrameworkVersion, Domain
        self.company = Company.objects.create(name='Co', cr_number='9090909090', sector='technology',
                                              size='small', contact_email='co@x.com')
        self.user = User.objects.create_user(email='co_off@x.com', password='longenough12',
                                             role='compliance_officer', company=self.company)
        self.client.force_login(self.user)
        self.fw = Framework.objects.create(code='NCA', name='NCA Essential Cybersecurity Controls')
        self.fv = FrameworkVersion.objects.create(code='NCA-ECC-2-2024', framework=self.fw,
                                                   version_label='ECC')
        self.dom = Domain.objects.create(framework=self.fw, code='D', name='D')

    def _control(self, cid):
        from compliance.models import Control
        return Control.objects.create(framework=self.fw, framework_version=self.fv, domain=self.dom,
                                      control_id=cid, title='t', description='d')

    def _approve_scope(self, company=None):
        from compliance.models import CompanyFrameworkScope
        return CompanyFrameworkScope.objects.create(company=company or self.company,
                                                    framework_version=self.fv, status='approved')

    def _plan(self, control, scope, company=None):
        from compliance.models import ControlApplicabilityResult
        return ControlApplicabilityResult.objects.create(company=company or self.company,
                                                         framework_scope=scope, control=control,
                                                         decision='applicable')

    def _url(self):
        return reverse('dashboard:main')

    def test_no_approved_scope_shows_scope_message_and_no_cards(self):
        resp = self.client.get(self._url())
        self.assertContains(resp, 'لم يتم اعتماد نطاق الأطر بعد')
        self.assertContains(resp, 'مراجعة واعتماد نطاق الأطر')
        self.assertNotContains(resp, 'إجمالي الضوابط')
        self.assertNotContains(resp, 'تشغيل تحليل الفجوات')
        self.assertFalse(resp.context['has_approved_scope'])

    def test_approved_scope_without_plan_shows_plan_message(self):
        self._approve_scope()
        resp = self.client.get(self._url())
        self.assertContains(resp, 'خطة الضوابط لم تُنشأ بعد')
        self.assertContains(resp, 'إنشاء خطة الضوابط')
        self.assertNotContains(resp, 'تشغيل تحليل الفجوات')

    def test_plan_ready_shows_real_counts_and_only_approved_frameworks(self):
        from compliance.models import CompanyControl
        scope = self._approve_scope()
        c1, c2 = self._control('ECC-1'), self._control('ECC-2')
        self._plan(c1, scope); self._plan(c2, scope)
        CompanyControl.objects.create(company=self.company, control=c1, status='compliant')
        resp = self.client.get(self._url())
        self.assertContains(resp, 'إجمالي الضوابط')
        self.assertContains(resp, 'الضوابط الأساسية للأمن السيبراني')  # ECC Arabic display name
        self.assertContains(resp, 'تشغيل تحليل الفجوات')
        self.assertEqual(resp.context['total_controls'], 2)
        self.assertEqual(resp.context['compliant_controls'], 1)
        self.assertEqual(resp.context['status_counts']['not_started'], 1)

    def test_legacy_frameworks_never_appear(self):
        from compliance.models import Framework
        Framework.objects.create(code='LEGACY', name='Legacy Bootstrap (Consolidated Excel)',
                                 is_active=True)
        scope = self._approve_scope()
        self._plan(self._control('ECC-1'), scope)
        resp = self.client.get(self._url())
        self.assertNotContains(resp, 'Legacy Bootstrap')
        self.assertNotContains(resp, 'Consolidated Excel')

    def test_no_success_message_when_no_controls(self):
        resp = self.client.get(self._url())
        self.assertNotContains(resp, 'عمل رائع')

    def test_gap_analysis_hidden_when_no_plan(self):
        self._approve_scope()
        resp = self.client.get(self._url())
        self.assertNotContains(resp, 'تشغيل تحليل الفجوات')

    def test_dashboard_scoped_to_own_company_only(self):
        from compliance.models import Company as _C
        other = Company.objects.create(name='Other', cr_number='7070707070', sector='technology',
                                       size='small', contact_email='o@x.com')
        oscope = self._approve_scope(company=other)
        self._plan(self._control('ECC-OTHER'), oscope, company=other)
        resp = self.client.get(self._url())
        self.assertContains(resp, 'لم يتم اعتماد نطاق الأطر بعد')  # own company has no scope
        self.assertEqual(resp.context['total_controls'], 0)
