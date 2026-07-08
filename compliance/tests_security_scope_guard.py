"""UAT-COMPANY-SECURITY-SCOPE-GUARD-FIX-A — role/isolation/email-verify/scope/audit guards."""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company, AuditLog
from compliance.models import (Evidence, CompanyFrameworkScope, Framework, FrameworkVersion)
from compliance.tests import (_company_with_control, _journey_user, _company_with_submission)


def _pdf():
    return SimpleUploadedFile('p.pdf', b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n%%EOF')


def _other_company():
    n = Company.objects.count() + 1
    return Company.objects.create(name=f'Other{n}', cr_number=f'{n:010d}', sector='technology',
                                  size='small', contact_email=f'o{n}@x.com')


class RoleAccessGuardTests(TestCase):
    def test_company_user_cannot_access_auditor_portal(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='ra1@x.com'))
        self.assertNotEqual(self.client.get(reverse('auditor_portal:dashboard')).status_code, 200)

    def test_company_user_cannot_access_platform_admin(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='ra2@x.com'))
        self.assertNotEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 200)

    def test_company_user_cannot_post_platform_admin_action(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='ra3@x.com'))
        r = self.client.post(reverse('platform_admin:add_note', args=[c.id]), {'note': 'x'})
        self.assertNotEqual(r.status_code, 200)   # blocked before any effect

    def test_auditor_not_routed_into_company_onboarding(self):
        from auditors.models import AuditorProfile
        u = User.objects.create_user(email='ra4@x.com', password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=u, full_name='A', status='active')
        self.client.force_login(u)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auditor/', resp.url)   # auditor -> auditor portal, NOT company onboarding

    def test_staff_not_treated_as_company(self):
        u = User.objects.create_user(email='rastaff@x.com', password='longenough12', is_staff=True)
        self.client.force_login(u)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/platform-admin/', resp.url)


class CrossCompanyIsolationTests(TestCase):
    def test_company_a_cannot_view_company_b_submission(self):
        cA, itemA, subA = _company_with_submission(fv_code='NCA-ECC-2-2024')
        cB = _other_company()
        self.client.force_login(_journey_user(cB, email='ccb@x.com'))
        r = self.client.get(reverse('compliance:evidence_submission_detail', args=[subA.id]))
        self.assertEqual(r.status_code, 404)   # no cross-company read; no name/data leak


class EmailVerificationGateTests(TestCase):
    def test_unverified_can_view_onboarding(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='ev1@x.com', email_verified=False))
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_unverified_can_view_intake(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='ev1b@x.com', email_verified=False))
        self.assertEqual(self.client.get(reverse('compliance:intake')).status_code, 200)

    def test_unverified_cannot_upload_evidence(self):
        c, control = _company_with_control()
        self.client.force_login(_journey_user(c, email='ev2@x.com', email_verified=False))
        r = self.client.post(reverse('compliance:upload_evidence', args=[control.id]),
                             {'evidence_file': _pdf()})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/onboarding', r.url)
        self.assertEqual(Evidence.objects.count(), 0)      # blocked — nothing stored

    def test_verified_can_upload_evidence(self):
        c, control = _company_with_control()
        self.client.force_login(_journey_user(c, email='ev3@x.com'))   # verified by default
        with mock.patch('compliance.services.process_evidence_pipeline'):
            r = self.client.post(reverse('compliance:upload_evidence', args=[control.id]),
                                 {'evidence_file': _pdf()})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Evidence.objects.count(), 1)


class ScopeApprovalGuardTests(TestCase):
    def _approved_scope(self, c):
        fw = Framework.objects.get_or_create(code='NCA', defaults={'name': 'NCA'})[0]
        fv = FrameworkVersion.objects.get_or_create(
            code='NCA-ECC-2-2024', defaults={'framework': fw})[0]
        return CompanyFrameworkScope.objects.create(company=c, framework_version=fv, status='approved')

    def test_intake_change_invalidates_approved_scope(self):
        c, _ = _company_with_control()
        scope = self._approved_scope(c)
        self.client.force_login(_journey_user(c, email='sa1@x.com'))
        self.client.post(reverse('compliance:intake'), {'uses_cloud_services': 'on'})
        scope.refresh_from_db()
        self.assertEqual(scope.status, 'needs_review')     # must be re-approved

    def test_intake_save_creates_audit_event(self):
        c, _ = _company_with_control()
        self.client.force_login(_journey_user(c, email='sa2@x.com'))
        self.client.post(reverse('compliance:intake'), {'has_remote_work': 'on'})
        self.assertTrue(AuditLog.objects.filter(company=c, action='intake_saved').exists())

    def test_evidence_checklist_requires_approved_scope(self):
        from compliance.evidence_planning import generate_evidence_checklist_for_framework_scope
        c, _ = _company_with_control()
        fw = Framework.objects.get_or_create(code='NCA', defaults={'name': 'NCA'})[0]
        fv = FrameworkVersion.objects.get_or_create(
            code='NCA-ECC-2-2024', defaults={'framework': fw})[0]
        scope = CompanyFrameworkScope.objects.create(company=c, framework_version=fv, status='proposed')
        res = generate_evidence_checklist_for_framework_scope(scope, apply=True)
        self.assertEqual(res['status'], 'skipped')         # not approved -> no checklist generated
