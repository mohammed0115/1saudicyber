"""Phase 4C — auditor onboarding + assignment tests."""
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company
from billing.subscription_access import activate_company_subscription
from auditors.models import AuditorProfile, AuditorAssignment
from auditors import services

# Reuse proven compliance fixtures (self-seeding).
from compliance.tests import _company_with_assessments, _journey_user, _company_with_submission


def _auditor(status='active', available=True, full_name=None):
    n = User.objects.count() + 1
    u = User.objects.create_user(username=f'aud{n}@x.com', email=f'aud{n}@x.com',
                                 password='longenough12', role='auditor')
    p = AuditorProfile.objects.create(
        user=u, full_name=full_name or f'Auditor {n}', status=status, is_available=available)
    return u, p


def _company_user(subscribe=True):
    c, fv, scope = _company_with_assessments()
    if subscribe:
        activate_company_subscription(c, 'Plan', days=30)
    return c, _journey_user(c)


def _assignment(company, auditor, status='requested'):
    return AuditorAssignment.objects.create(company=company, auditor=auditor, status=status)


class AuditorRegistrationTests(TestCase):
    def _payload(self, **over):
        d = {'full_name': 'مدقّق تجريبي', 'email': 'newaud@x.com',
             'password': 'longenough123', 'password_confirm': 'longenough123',
             'organization_name': 'Org', 'license_or_membership_no': 'L1',
             'city': 'Riyadh', 'specialization': 'NCA', 'bio': 'x'}
        d.update(over)
        return d

    def test_auditor_registration_page_renders(self):
        resp = self.client.get(reverse('auditors:register'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'التسجيل كمدقّق')

    def test_auditor_registration_creates_user_and_profile(self):
        resp = self.client.post(reverse('auditors:register'), self._payload())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(email='newaud@x.com').exists())
        self.assertTrue(AuditorProfile.objects.filter(user__email='newaud@x.com').exists())

    def test_auditor_profile_defaults_pending_review(self):
        self.client.post(reverse('auditors:register'), self._payload())
        p = AuditorProfile.objects.get(user__email='newaud@x.com')
        self.assertEqual(p.status, 'pending_review')

    def test_auditor_onboarding_requires_login(self):
        resp = self.client.get(reverse('auditors:onboarding'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_authenticated_company_user_cannot_submit_auditor_registration(self):
        # A logged-in company user must NOT create a new auditor or switch session.
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        before_users = User.objects.count()
        before_auditors = AuditorProfile.objects.count()
        resp = self.client.post(reverse('auditors:register'),
                                self._payload(email='switcher@x.com'))
        self.assertEqual(resp.status_code, 200)  # blocked page, not a redirect into a new session
        self.assertFalse(User.objects.filter(email='switcher@x.com').exists())
        self.assertEqual(User.objects.count(), before_users)
        self.assertEqual(AuditorProfile.objects.count(), before_auditors)
        # Session is unchanged: still the company user.
        self.assertEqual(int(self.client.session['_auth_user_id']), cu.id)

    def test_authenticated_company_user_sees_clear_block_message(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:register'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'تسجيل الخروج أولًا')

    def test_existing_auditor_visiting_register_goes_to_onboarding(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:register'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('auditors:onboarding'), resp.url)

    def test_logout_with_next_returns_to_register(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.post(reverse('core:logout') + '?next=' + reverse('auditors:register'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('auditors:register'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_ignores_unsafe_next(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.post(reverse('core:logout') + '?next=https://evil.example/x')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('core:landing'))

    def test_pending_auditor_cannot_view_company_data(self):
        u, p = _auditor(status='pending_review')
        c, fv, scope = _company_with_assessments()
        _assignment(c, p, status='accepted')  # even if accepted, pending profile sees nothing
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'لا يتيح الوصول إلى بيانات الشركات')


class AuditorStatusListingTests(TestCase):
    def test_active_auditor_can_be_listed(self):
        _u, p = _auditor(status='active', available=True)
        self.assertIn(p, list(services.list_available_auditors()))

    def test_suspended_auditor_not_available_for_assignment(self):
        _u, p = _auditor(status='suspended')
        self.assertNotIn(p, list(services.list_available_auditors()))

    def test_inactive_unavailable_auditor_not_listed(self):
        _u, p1 = _auditor(status='inactive')
        _u2, p2 = _auditor(status='active', available=False)
        avail = list(services.list_available_auditors())
        self.assertNotIn(p1, avail)
        self.assertNotIn(p2, avail)


class AssignmentTests(TestCase):
    def test_subscribed_company_can_view_available_auditors(self):
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor(full_name='AvailAuditor')
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AvailAuditor')

    def test_unsubscribed_company_cannot_assign_auditor(self):
        c, cu = _company_user(subscribe=False)
        _u, p = _auditor()
        self.client.force_login(cu)
        resp = self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertContains(resp, 'تفعيل الاشتراك مطلوب')
        self.assertEqual(AuditorAssignment.objects.filter(company=c).count(), 0)

    def test_subscribed_company_can_assign_auditor(self):
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=c, auditor=p, status='requested').count(), 1)

    def test_duplicate_active_assignment_prevented(self):
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=c, auditor=p).count(), 1)

    def test_company_user_cannot_assign_for_other_company(self):
        # assign() always uses request.user.company; it can never target another company.
        a, au = _company_user(subscribe=True)
        b, bu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(bu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=a).count(), 0)
        self.assertEqual(AuditorAssignment.objects.filter(company=b).count(), 1)

    def test_auditor_can_view_own_assignment(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p)
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('auditors:assignment_detail', args=[a.id])).status_code, 200)

    def test_auditor_cannot_view_other_auditor_assignment(self):
        u1, p1 = _auditor(status='active')
        u2, p2 = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p2)  # belongs to auditor 2
        self.client.force_login(u1)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertEqual(resp.status_code, 302)  # not yours -> redirect

    def test_auditor_can_accept_assignment(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p)
        self.client.force_login(u)
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]), {'action': 'accept'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'accepted')

    def test_auditor_can_reject_assignment(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p)
        self.client.force_login(u)
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]), {'action': 'reject'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'rejected')

    def test_cancelled_assignment_no_longer_grants_access(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p, status='cancelled')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertNotContains(resp, 'سياق الشركة')


class AuditorContextAccessTests(TestCase):
    def test_assigned_auditor_can_view_assigned_report_context(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'سياق الشركة')

    def test_unassigned_auditor_cannot_view_company_report_context(self):
        u1, p1 = _auditor(status='active')
        u2, p2 = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p2, status='accepted')
        self.client.force_login(u1)  # not assigned to this
        self.assertEqual(self.client.get(reverse('auditors:assignment_detail', args=[a.id])).status_code, 302)

    def test_pending_auditor_cannot_view_assigned_report_context_until_active(self):
        u, p = _auditor(status='pending_review')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertNotContains(resp, 'سياق الشركة')

    def test_assignment_does_not_bypass_subscription_report_exports(self):
        # An auditor has no company, so company export endpoints never serve them a file.
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        _assignment(c, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertNotEqual(resp.get('Content-Type'), 'text/csv')


class AuditorSecurityTests(TestCase):
    def test_assignment_views_require_login(self):
        for n in ['auditors:list', 'auditors:dashboard', 'auditors:onboarding']:
            resp = self.client.get(reverse(n))
            self.assertEqual(resp.status_code, 302, n)
            self.assertIn('/login', resp.url, n)

    def test_assignment_actions_are_tenant_scoped(self):
        # A company user (no auditor profile) cannot reach the auditor dashboard data.
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 302)  # redirected to auditor registration

    def test_auditor_assignment_does_not_create_companycontrol(self):
        from compliance.models import CompanyControl
        before = CompanyControl.objects.count()
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(CompanyControl.objects.count(), before)

    def test_auditor_assignment_does_not_change_controlassessment_status(self):
        from compliance.models import ControlAssessment
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        before = {a.id: a.status for a in ControlAssessment.objects.filter(company=c)}
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        after = {a.id: a.status for a in ControlAssessment.objects.filter(company=c)}
        self.assertEqual(before, after)

    def test_auditor_assignment_does_not_use_ai_final_decision(self):
        from compliance.models import EvidenceAnalysisResult, ControlAssessment
        c, cu = _company_user(subscribe=True)
        u, p = _auditor(status='active')
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertEqual(EvidenceAnalysisResult.objects.filter(company=c).count(), 0)
        self.assertEqual(ControlAssessment.objects.filter(company=c, status='compliant').count(), 0)


class AuditorUxTests(TestCase):
    def test_assign_auditor_button_visible_when_subscribed(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.get(reverse('compliance:reports_index'))
        self.assertContains(resp, 'إسناد الملف إلى مدقق داخل المنصة')

    def test_subscription_required_message_when_unsubscribed(self):
        c, cu = _company_user(subscribe=False)
        self.client.force_login(cu)
        resp = self.client.get(reverse('compliance:reports_index'))
        self.assertContains(resp, 'تفعيل الاشتراك')

    def test_auditor_registration_loading_state_present(self):
        resp = self.client.get(reverse('auditors:register'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ إرسال طلب التسجيل كمدقق')

    def test_assignment_loading_state_present(self):
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:list'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ إسناد الملف إلى المدقق')

    def test_auditor_pages_are_arabic_rtl(self):
        self.assertContains(self.client.get(reverse('auditors:register')), 'dir="rtl"')


class Phase4CBackwardCompatTests(TestCase):
    def setUp(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())

    def _register_company(self, cr='2121212121', email='bc4c@co.example'):
        return self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': email,
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': cr,
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

    def test_company_registration_still_works(self):
        resp = self._register_company()
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='2121212121').exists())

    def test_onboarding_still_works(self):
        self._register_company(cr='2222212121', email='bc4c2@co.example')
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_subscription_gated_reports_still_work(self):
        c, cu = _company_user(subscribe=False)
        self.client.force_login(cu)
        self.assertContains(self.client.get(reverse('compliance:report_executive_summary')),
                            'تفعيل الاشتراك مطلوب')

    def test_arabic_public_pages_still_work(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, 'جاهزية الامتثال')
        self.assertContains(resp, 'dir="rtl"')

    def test_evidence_upload_v2_still_works(self):
        from compliance.models import EvidenceSubmission
        c, item, sub = _company_with_submission()
        self.assertTrue(EvidenceSubmission.objects.filter(id=sub.id).exists())

    def test_advisory_analysis_still_works(self):
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        analyze_evidence_submission(sub, apply=True)
        self.assertTrue(EvidenceAnalysisResult.objects.filter(evidence_submission=sub).exists())

    def test_auditor_assessment_staff_flow_still_works(self):
        from compliance.control_assessment import update_assessment_from_auditor_input
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        staff = _journey_user(c, email='staff4c@x.com', is_staff=True)
        update_assessment_from_auditor_input(a, {'status': 'compliant'}, staff)
        a.refresh_from_db()
        self.assertEqual(a.status, 'compliant')

    def test_reports_still_work(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        self.assertEqual(self.client.get(reverse('compliance:report_executive_summary')).status_code, 200)
