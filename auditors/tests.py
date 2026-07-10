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
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]),
                         {'action': 'reject', 'reason': 'خارج نطاق تخصّصي'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'rejected')
        self.assertEqual(a.response_note, 'خارج نطاق تخصّصي')

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
        self.assertContains(resp, 'جارٍ إرسال طلب المراجعة')

    def test_auditor_pages_are_arabic_rtl(self):
        self.assertContains(self.client.get(reverse('auditors:register')), 'dir="rtl"')


class GuidedAuditorWorkflowTests(TestCase):
    """Phase 8D-2-FIX-C — auditor guided journey: pending + no-assignment guidance."""

    def test_journey_builder_anonymous_and_steps(self):
        from django.contrib.auth.models import AnonymousUser
        from auditors.journey import build_auditor_journey
        j = build_auditor_journey(AnonymousUser())
        self.assertEqual(j['total'], 10)
        self.assertEqual(j['current_step']['key'], 'registration')
        self.assertFalse(j['has_profile'])

    def test_pending_auditor_dashboard_shows_activation_guidance(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'حسابك قيد مراجعة إدارة منصة 1SaudiCyber لدى شركة احصل الحل')
        self.assertContains(resp, 'بعد التفعيل ستظهر لك ملفات الشركات المسندة')

    def test_active_auditor_no_assignments_shows_guidance(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'لا توجد طلبات مراجعة بانتظار موافقتك حاليًا')
        self.assertContains(resp, 'لا توجد شركات مقبولة بعد')

    def test_pending_journey_marks_dashboard_step_blocked(self):
        u, p = _auditor(status='pending_review')
        from auditors.journey import build_auditor_journey
        j = build_auditor_journey(u)
        by_key = {s['key']: s for s in j['steps']}
        self.assertEqual(by_key['registration']['status'], 'completed')
        self.assertEqual(by_key['pending_activation']['status'], 'current')
        self.assertEqual(by_key['dashboard']['status'], 'blocked')
        self.assertEqual(by_key['final_verdict']['status'], 'blocked')

    def test_active_with_accepted_assignment_unblocks_review(self):
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        _assignment(c, p, status='accepted')
        from auditors.journey import build_auditor_journey
        j = build_auditor_journey(u)
        by_key = {s['key']: s for s in j['steps']}
        self.assertEqual(by_key['assigned_files']['status'], 'completed')
        self.assertEqual(by_key['final_verdict']['status'], 'current')

    def test_auditor_dashboard_renders_journey_stepper(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertContains(resp, 'مسار المراجعة الموجّه')

    def test_auditor_pages_safe_internal_review_wording(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        body = self.client.get(reverse('auditors:dashboard')).content.decode()
        self.assertIn('مراجعة داخلية', body)
        for banned in ('معتمد من NCA', 'اعتماد حكومي', 'official accreditation',
                       'certified by NCA'):
            self.assertNotIn(banned, body)

    def test_register_page_shows_journey_roadmap(self):
        resp = self.client.get(reverse('auditors:register'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'مسار المراجعة الموجّه')


class PlatformAdminAuditorApprovalTests(TestCase):
    """Phase 8D-3A — Get Solution platform-admin auditor approval workflow."""

    def _staff(self, email='gsadmin@x.com', superuser=False):
        u = User.objects.create_user(username=email, email=email, password='longenough12',
                                     role='admin', is_staff=True, is_superuser=superuser)
        return u

    # ---- access control ----
    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('platform_admin:auditor_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_staff_can_access_list(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'إدارة اعتماد المدققين')

    def test_superuser_can_access_list(self):
        self.client.force_login(self._staff(email='su@x.com', superuser=True))
        self.assertEqual(self.client.get(reverse('platform_admin:auditor_list')).status_code, 200)

    def test_company_user_denied(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.get(reverse('platform_admin:auditor_list'))
        self.assertEqual(resp.status_code, 403)

    def test_auditor_user_denied(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('platform_admin:auditor_list')).status_code, 403)

    def test_normal_authenticated_user_denied(self):
        u = User.objects.create_user(username='plain@x.com', email='plain@x.com',
                                     password='longenough12', role='company_admin')
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('platform_admin:auditor_list')).status_code, 403)

    # ---- listing ----
    def test_pending_auditor_appears_in_list(self):
        u, p = _auditor(status='pending_review', full_name='PendingAud')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_list') + '?status=pending_review')
        self.assertContains(resp, 'PendingAud')

    def test_summary_counts_render(self):
        _auditor(status='pending_review')
        _auditor(status='active')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_list'))
        self.assertContains(resp, 'قيد المراجعة')
        self.assertContains(resp, 'مفعّل')

    # ---- actions ----
    def test_approve_changes_pending_to_active(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]),
                         {'action': 'approve'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_approve_writes_audit_log(self):
        from core.models import AuditLog
        u, p = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]), {'action': 'approve'})
        log = AuditLog.objects.filter(action='auditor_approve').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('new_status'), 'active')
        self.assertEqual(log.metadata.get('old_status'), 'pending_review')

    def test_reject_requires_reason(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        # No reason -> rejected (declined) must NOT happen.
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]), {'action': 'reject'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'pending_review')
        # With reason -> inactive (declined).
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]),
                         {'action': 'reject', 'reason': 'بيانات غير مكتملة'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'inactive')

    def test_suspend_requires_reason(self):
        u, p = _auditor(status='active')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]), {'action': 'suspend'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]),
                         {'action': 'suspend', 'reason': 'مخالفة سياسة'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'suspended')

    def test_reactivate_suspended_to_active(self):
        u, p = _auditor(status='suspended')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]), {'action': 'reactivate'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_company_user_cannot_perform_action(self):
        c, cu = _company_user(subscribe=True)
        u, p = _auditor(status='pending_review')
        self.client.force_login(cu)
        resp = self.client.post(reverse('platform_admin:auditor_action', args=[p.id]),
                                {'action': 'approve'})
        self.assertEqual(resp.status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.status, 'pending_review')  # unchanged

    def test_detail_page_shows_actions(self):
        u, p = _auditor(status='pending_review', full_name='DetailAud')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_detail', args=[p.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'DetailAud')
        self.assertContains(resp, 'اعتماد وتفعيل')

    # ---- safety ----
    def test_no_unsafe_certification_wording_on_admin_pages(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        banned = ['معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد رسمي',
                  'اعتماد حكومي', 'certified by NCA', 'official accreditation', 'government accredited']
        for url in (reverse('platform_admin:auditor_list'),
                    reverse('platform_admin:auditor_detail', args=[p.id])):
            body = self.client.get(url).content.decode()
            for w in banned:
                self.assertNotIn(w, body, '%s in %s' % (w, url))

    def test_get_solution_ownership_wording_present(self):
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:auditor_list')).content.decode()
        self.assertIn('شركة احصل الحل', body)

    # ---- regression: registration flows intact ----
    def test_anonymous_auditor_registration_still_works(self):
        resp = self.client.post(reverse('auditors:register'), {
            'full_name': 'مدقق جديد', 'email': 'freshaud@x.com',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'city': 'Riyadh'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AuditorProfile.objects.filter(user__email='freshaud@x.com',
                                                      status='pending_review').exists())

    def test_company_user_cannot_switch_into_auditor_registration(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        before = User.objects.count()
        resp = self.client.post(reverse('auditors:register'), {
            'full_name': 'X', 'email': 'switch2@x.com',
            'password': 'longenough123', 'password_confirm': 'longenough123'})
        self.assertEqual(resp.status_code, 200)  # blocked page
        self.assertFalse(User.objects.filter(email='switch2@x.com').exists())
        self.assertEqual(User.objects.count(), before)


class GetSolutionCRMConsoleTests(TestCase):
    """Phase 8D-3B-ADMIN-CRM-A — read-only Get Solution CRM console foundation."""

    def _staff(self, email='crmadmin@x.com', superuser=False):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True, is_superuser=superuser)

    CRM_URLS = ('platform_admin:dashboard', 'platform_admin:companies_list',
                'platform_admin:unlinked_accounts')

    # ---- access control ----
    def test_anonymous_denied_from_dashboard(self):
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_company_user_denied(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        for name in self.CRM_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_auditor_user_denied(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        for name in self.CRM_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_staff_can_access_dashboard(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'وحدة التشغيل الداخلية')

    def test_superuser_can_access_dashboard(self):
        self.client.force_login(self._staff(email='su2@x.com', superuser=True))
        self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 200)

    # ---- companies ----
    def test_staff_can_access_companies_list(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:companies_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'الشركات')
        self.assertContains(resp, c.name)

    def test_staff_can_access_company_detail(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, c.name)
        self.assertContains(resp, cu.email)  # linked user shown
        self.assertContains(resp, 'الحالة التشغيلية')

    def test_companies_list_no_500_when_empty(self):
        # No companies at all -> must render an empty-state, not crash.
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:companies_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'لا توجد شركات مسجّلة بعد')

    def test_dashboard_no_500_with_no_data(self):
        self.client.force_login(self._staff())
        self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 200)

    # ---- unlinked accounts (solves "No Company Associated") ----
    def test_unlinked_accounts_renders_and_lists_unlinked_user(self):
        # A company_admin role user with NO company is exactly the "No Company Associated" case.
        orphan = User.objects.create_user(username='orphan@x.com', email='orphan@x.com',
                                          password='longenough12', role='company_admin')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:unlinked_accounts'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'حسابات غير مرتبطة')
        self.assertContains(resp, 'orphan@x.com')

    def test_unlinked_excludes_company_linked_and_auditors_and_staff(self):
        from auditors.crm_services import unlinked_users
        c, cu = _company_user(subscribe=True)           # linked -> excluded
        au, ap = _auditor(status='active')              # auditor -> excluded
        staff = self._staff(email='exadmin@x.com')      # staff -> excluded
        orphan = User.objects.create_user(username='lonely@x.com', email='lonely@x.com',
                                          password='longenough12', role='company_admin')
        ids = set(unlinked_users().values_list('id', flat=True))
        self.assertIn(orphan.id, ids)
        self.assertNotIn(cu.id, ids)
        self.assertNotIn(au.id, ids)
        self.assertNotIn(staff.id, ids)

    # ---- overview/listing pages stay read-only (no platform-admin POST forms) ----
    # NOTE: company_detail is intentionally an ACTION page from Phase 8D-3D-CRM-B
    # (it hosts the guarded link/unlink POST forms), so it is excluded here.
    def test_crm_listing_views_are_get_only_readonly(self):
        self.client.force_login(self._staff())
        for name, args in (('platform_admin:dashboard', []),
                           ('platform_admin:companies_list', []),
                           ('platform_admin:unlinked_accounts', [])):
            body = self.client.get(reverse(name, args=args)).content.decode()
            self.assertNotIn('action="/platform-admin', body, name)
            self.assertNotIn("action='/platform-admin", body, name)

    # ---- safety wording ----
    def test_no_unsafe_certification_wording_on_crm_pages(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(self._staff())
        banned = ['معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد رسمي',
                  'اعتماد حكومي', 'certified by NCA', 'official accreditation',
                  'government accredited', 'official certification']
        urls = [reverse('platform_admin:dashboard'),
                reverse('platform_admin:companies_list'),
                reverse('platform_admin:company_detail', args=[c.id]),
                reverse('platform_admin:unlinked_accounts')]
        for url in urls:
            body = self.client.get(url).content.decode()
            for w in banned:
                self.assertNotIn(w, body, '%s in %s' % (w, url))


class PlatformAdminCRMNavigationTests(TestCase):
    """Phase 8D-3B-UI-FIX-A — platform-admin pages use the CRM layout, not the
    customer/compliance navbar."""

    def _staff(self, email='navadmin@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    # Customer/compliance navbar links that must NEVER appear on platform-admin pages.
    CUSTOMER_NAV_LINKS = ('/compliance/dashboard/', '/compliance/reports/',
                          '/compliance/evidence-checklist/', '/monitoring/')

    def _crm_urls(self, company_id):
        return [reverse('platform_admin:dashboard'),
                reverse('platform_admin:companies_list'),
                reverse('platform_admin:company_detail', args=[company_id]),
                reverse('platform_admin:unlinked_accounts'),
                reverse('platform_admin:auditor_list')]

    def test_dashboard_renders_crm_navigation(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'نظرة عامة')
        self.assertContains(resp, 'وحدة التشغيل الداخلية')

    def test_auditors_page_renders_crm_navigation(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_list'))
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'الشركات')

    def test_companies_page_renders_crm_navigation(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:companies_list'))
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'حسابات غير مرتبطة')

    def test_unlinked_page_renders_crm_navigation(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:unlinked_accounts'))
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'المدققون')

    def test_platform_admin_pages_have_no_customer_compliance_nav(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(self._staff())
        for url in self._crm_urls(c.id):
            body = self.client.get(url).content.decode()
            # Distinctive customer-nav label (nav-only; never CRM content):
            self.assertNotIn('مسار الامتثال', body, url)
            # Customer-nav links must be absent:
            for link in self.CUSTOMER_NAV_LINKS:
                self.assertNotIn(link, body, '%s in %s' % (link, url))

    def test_auditor_approval_workflow_still_works(self):
        u, p = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        # detail page renders under the CRM layout
        resp = self.client.get(reverse('platform_admin:auditor_detail', args=[p.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Get Solution CRM')
        # approve action still works
        self.client.post(reverse('platform_admin:auditor_action', args=[p.id]), {'action': 'approve'})
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_denied_page_shows_neither_customer_nor_full_crm_compliance_nav(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(resp.status_code, 403)
        body = resp.content.decode()
        self.assertNotIn('مسار الامتثال', body)
        for link in self.CUSTOMER_NAV_LINKS:
            self.assertNotIn(link, body)

    def test_no_unsafe_certification_wording_in_crm_layout(self):
        c, cu = _company_user(subscribe=True)
        self.client.force_login(self._staff())
        banned = ['معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد رسمي',
                  'اعتماد حكومي', 'certified by NCA', 'official accreditation',
                  'government accredited', 'official certification']
        for url in self._crm_urls(c.id):
            body = self.client.get(url).content.decode()
            for w in banned:
                self.assertNotIn(w, body, '%s in %s' % (w, url))


class CRMCompanyUserLinkingTests(TestCase):
    """Phase 8D-3D-CRM-B — Get Solution CRM company/user link & unlink actions."""

    def _staff(self, email='linkadmin@x.com', superuser=False):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True, is_superuser=superuser)

    def _company(self, cr='7171717171', name='Link Co'):
        return Company.objects.create(name=name, cr_number=cr, sector='technology',
                                      size='small', contact_email='link@co.example')

    def _unlinked_user(self, email='free@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='company_admin')

    def _link_url(self, c):
        return reverse('platform_admin:link_user', args=[c.id])

    def _unlink_url(self, c):
        return reverse('platform_admin:unlink_user', args=[c.id])

    def _co_admin(self, c, email='coadmin@x.com'):
        # A second active company_admin so a target is not the LAST admin (unlink guard).
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='company_admin', company=c)

    # ---- permissions ----
    def test_anonymous_cannot_link(self):
        c = self._company()
        r = self.client.post(self._link_url(c), {'user_id': 1, 'reason': 'x'})
        self.assertIn(r.status_code, (302, 403))
        if r.status_code == 302:
            self.assertIn('/login', r.url)

    def test_company_user_cannot_link(self):
        c = self._company()
        u = self._unlinked_user('cu2@x.com'); u.company = c; u.save()
        self.client.force_login(u)
        self.assertEqual(self.client.post(self._link_url(c),
                         {'user_id': 1, 'reason': 'x'}).status_code, 403)

    def test_auditor_user_cannot_link(self):
        c = self._company()
        au = User.objects.create_user(username='al@x.com', email='al@x.com',
                                      password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=au, full_name='A', status='active')
        self.client.force_login(au)
        self.assertEqual(self.client.post(self._link_url(c),
                         {'user_id': 1, 'reason': 'x'}).status_code, 403)

    def test_link_requires_post(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.assertEqual(self.client.get(self._link_url(c)).status_code, 405)

    # ---- linking ----
    def test_staff_can_link_eligible_user(self):
        c = self._company()
        u = self._unlinked_user()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': 'رقم الطلب 123'})
        u.refresh_from_db()
        self.assertEqual(u.company_id, c.id)

    def test_link_requires_reason(self):
        c = self._company()
        u = self._unlinked_user()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': ''})
        u.refresh_from_db()
        self.assertIsNone(u.company_id)

    def test_link_rejects_staff_target(self):
        c = self._company()
        target = self._staff(email='targetstaff@x.com')
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': target.id, 'reason': 'x'})
        target.refresh_from_db()
        self.assertIsNone(target.company_id)

    def test_link_rejects_auditor_target(self):
        c = self._company()
        au = User.objects.create_user(username='at@x.com', email='at@x.com',
                                      password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=au, full_name='A', status='active')
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': au.id, 'reason': 'x'})
        au.refresh_from_db()
        self.assertIsNone(au.company_id)

    def test_link_rejects_already_linked_user(self):
        c1 = self._company(cr='7272727272', name='C1')
        c2 = self._company(cr='7373737373', name='C2')
        u = self._unlinked_user(); u.company = c1; u.save()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c2), {'user_id': u.id, 'reason': 'move'})
        u.refresh_from_db()
        self.assertEqual(u.company_id, c1.id)  # unchanged (fail closed)

    def test_link_missing_user_is_safe(self):
        c = self._company()
        self.client.force_login(self._staff())
        resp = self.client.post(self._link_url(c), {'user_id': 999999, 'reason': 'x'})
        self.assertEqual(resp.status_code, 302)  # no 500

    def test_link_does_not_change_session(self):
        c = self._company()
        u = self._unlinked_user()
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': 'r'})
        self.assertEqual(int(self.client.session['_auth_user_id']), staff.id)

    def test_linked_user_gone_from_unlinked_and_on_company_detail(self):
        c = self._company()
        u = self._unlinked_user()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': 'r'})
        # First GET flushes the transient success flash (which echoes the email);
        # the second GET reflects the steady-state list.
        self.client.get(reverse('platform_admin:unlinked_accounts'))
        unlinked = self.client.get(reverse('platform_admin:unlinked_accounts')).content.decode()
        self.assertNotIn(u.email, unlinked)
        self.assertIn('لا توجد حسابات غير مرتبطة حاليًا', unlinked)
        detail = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn(u.email, detail)

    def test_linked_user_can_reach_company_dashboard(self):
        c = self._company()
        u = self._unlinked_user()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': 'r'})
        self.client.logout()
        self.client.force_login(User.objects.get(id=u.id))
        self.assertEqual(self.client.get(reverse('compliance:classification')).status_code, 200)

    # ---- unlinking ----
    def test_staff_can_unlink_user(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)  # not the last admin
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'left company'})
        u.refresh_from_db()
        self.assertIsNone(u.company_id)

    def test_unlink_requires_post(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.assertEqual(self.client.get(self._unlink_url(c)).status_code, 405)

    def test_unlink_requires_reason(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': ''})
        u.refresh_from_db()
        self.assertEqual(u.company_id, c.id)  # unchanged

    def test_unlink_does_not_delete_user_or_company(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        self.assertTrue(User.objects.filter(id=u.id).exists())
        self.assertTrue(Company.objects.filter(id=c.id).exists())

    def test_unlinked_user_reappears_in_unlinked_list(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        body = self.client.get(reverse('platform_admin:unlinked_accounts')).content.decode()
        self.assertIn(u.email, body)

    def test_unlink_does_not_change_session(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        self.assertEqual(int(self.client.session['_auth_user_id']), staff.id)

    # ---- audit ----
    def test_link_writes_audit_log(self):
        from core.models import AuditLog
        c = self._company()
        u = self._unlinked_user()
        self.client.force_login(self._staff())
        self.client.post(self._link_url(c), {'user_id': u.id, 'reason': 'ticket 9'})
        log = AuditLog.objects.filter(action='crm_link_user').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('target_user_id'), u.id)
        self.assertEqual(log.metadata.get('new_company_id'), c.id)
        self.assertEqual(log.metadata.get('reason'), 'ticket 9')

    def test_unlink_writes_audit_log(self):
        from core.models import AuditLog
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'offboard'})
        log = AuditLog.objects.filter(action='crm_unlink_user').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('old_company_id'), c.id)
        self.assertEqual(log.metadata.get('reason'), 'offboard')

    def test_last_company_admin_cannot_be_unlinked(self):
        # Safety: unlinking the ONLY active company admin is blocked (would strand the company).
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()  # sole company_admin
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        u.refresh_from_db()
        self.assertEqual(u.company_id, c.id)  # still linked (blocked)

    def test_non_last_admin_can_be_unlinked(self):
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self._co_admin(c)
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        u.refresh_from_db()
        self.assertIsNone(u.company_id)

    def test_last_admin_unlink_block_is_not_audited_as_success(self):
        from core.models import AuditLog
        c = self._company()
        u = self._unlinked_user(); u.company = c; u.save()
        self.client.force_login(self._staff())
        self.client.post(self._unlink_url(c), {'user_id': u.id, 'reason': 'r'})
        self.assertFalse(AuditLog.objects.filter(action='crm_unlink_user',
                                                 metadata__target_user_id=u.id).exists())

    # ---- safety ----
    def test_company_detail_link_ui_no_unsafe_wording(self):
        c = self._company()
        self._unlinked_user()
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('ربط حساب بالشركة', body)
        # Affirmative certification/accreditation CLAIMS must never appear (the CRM
        # footer's negated disclaimer "لا يمثّل ... شهادة امتثال رسمية" is safe).
        for w in ('معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد حكومي',
                  'certified by NCA', 'official accreditation', 'government accredited',
                  'official certification'):
            self.assertNotIn(w, body)
        if 'شهادة امتثال رسمية' in body:
            self.assertIn('لا يمثّل اعتمادًا رسميًا أو شهادة امتثال رسمية', body)


class CRMCompanyJourneySummaryTests(TestCase):
    """UAT-ADMIN-COMPANY-DETAIL-STATUS-FIX-A — internal compliance-journey summary on the CRM
    company detail page (staff-only; never exposed to companies/auditors)."""

    def _staff(self, email='js_admin@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def _company(self, cr='6161616161'):
        return Company.objects.create(name='Journey Co', cr_number=cr, sector='technology',
                                      size='small', contact_email='j@co.example')

    def test_company_appears_in_crm_list_after_registration(self):
        c = self._company(cr='6060606060')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:companies_list')).content.decode()
        self.assertIn(c.name, body)

    def test_journey_summary_reflects_classification_and_scope(self):
        from compliance.models import (CompanyIntakeProfile, Framework, FrameworkVersion,
                                        CompanyFrameworkScope)
        c = self._company()
        cu = User.objects.create_user(username='jco@x.com', email='jco@x.com',
                                      password='longenough12', role='company_admin', company=c,
                                      email_verified=True)
        CompanyIntakeProfile.objects.create(company=c, uses_cloud_services=True)
        fw = Framework.objects.create(code='NCA', name='NCA')
        fv = FrameworkVersion.objects.create(code='NCA-ECC-2-2024', framework=fw, version_label='ECC')
        CompanyFrameworkScope.objects.create(company=c, framework_version=fv, status='approved')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ملخص رحلة الامتثال')
        self.assertContains(resp, 'حالة اعتماد النطاق')
        j = resp.context['journey']
        self.assertTrue(j['classification_done'])
        self.assertTrue(j['scope_approved'])
        self.assertTrue(j['email_verified'])
        self.assertGreater(j['proposed_frameworks'], 0)
        self.assertGreater(j['expected_controls'], 0)

    def test_onboarded_label_is_clarified_not_misleading(self):
        c = self._company(cr='6262626262')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('زر الترحيب فقط', body)                  # clarified, de-emphasized label
        self.assertNotIn('التهيئة مكتملة · Onboarded', body)   # old misleading label removed

    def test_company_user_cannot_access_company_detail(self):
        c = self._company(cr='6363636363')
        u = User.objects.create_user(username='cu9@x.com', email='cu9@x.com',
                                     password='longenough12', role='company_admin', company=c)
        self.client.force_login(u)
        self.assertEqual(self.client.get(
            reverse('platform_admin:company_detail', args=[c.id])).status_code, 403)


class CRMCompanyStateConsistencyTests(TestCase):
    """UAT-ADMIN-COMPANY-DETAIL-STATE-CONSISTENCY-FIX-A — the CRM journey summary must reflect the
    SAME source of truth (classify_company) as the company classification page."""

    def _staff(self, email='cons_admin@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def _company(self, cr='6161610000'):
        return Company.objects.create(name='Cons Co', cr_number=cr, sector='technology',
                                      size='small', contact_email='cons@co.example')

    def _company_with_intake(self, cr='6161610001', **profile):
        from compliance.models import CompanyIntakeProfile
        c = self._company(cr=cr)
        base = dict(uses_cloud_services=True, has_remote_work=True,
                    manages_official_social_media_accounts=True, works_with_aramco=True)
        base.update(profile)
        CompanyIntakeProfile.objects.create(company=c, **base)
        return c

    def test_admin_summary_matches_company_classification_numbers(self):
        from compliance.smart_classification import classify_company
        from auditors.crm_services import company_journey_summary
        c = self._company_with_intake(cr='6565650001')
        r = classify_company(c)
        j = company_journey_summary(c)
        self.assertEqual(j['proposed_frameworks'], r.recommended_count)
        self.assertEqual(j['expected_controls'], r.total_expected_controls)
        self.assertEqual(j['risk_level_ar'], r.risk_level_ar)
        # And the rendered admin page carries the same proposed count.
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertEqual(resp.context['journey']['proposed_frameworks'], r.recommended_count)

    def test_admin_shows_scope_not_approved_and_next_action(self):
        c = self._company_with_intake(cr='6767670001')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertContains(resp, 'غير معتمد')
        self.assertContains(resp, 'الخطوة التالية من جهة الشركة: اعتماد نطاق الأطر')

    def test_pre_plan_sections_show_unavailable_message(self):
        c = self._company_with_intake(cr='6868680001')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('المراحل اللاحقة غير متاحة قبل اعتماد النطاق وإنشاء خطة الضوابط', body)

    def test_summary_separates_proposed_and_approved(self):
        c = self._company_with_intake(cr='6969690001')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        for label in ('الأطر المقترحة', 'الأطر المعتمدة', 'الضوابط المتوقعة', 'الضوابط المنشأة فعليًا'):
            self.assertContains(resp, label)
        self.assertEqual(resp.context['journey']['approved_frameworks'], 0)
        self.assertFalse(resp.context['journey']['control_plan_generated'])

    def test_status_change_timeline_message_is_arabic(self):
        from auditors.crm_services import _activity_detail
        d = _activity_detail('crm_status_changed', {'old_status': 'onboarding', 'new_status': 'active'})
        self.assertEqual(d, 'من «تهيئة» إلى «نشطة»')

    def test_admin_stepper_current_step_is_scope_approval(self):
        # Classification done + proposed frameworks exist, scope not approved -> current = scope approval.
        c = self._company_with_intake(cr='7070700001')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        j = resp.context['journey']
        cur = next(s for s in j['steps'] if s['status'] == 'current')
        self.assertEqual(cur['key'], 'scope_approval')
        self.assertEqual(j['current_step_label'], 'بانتظار اعتماد نطاق الأطر')
        self.assertContains(resp, 'الإجراء التالي:')
        self.assertContains(resp, 'الشركة تحتاج اعتماد نطاق الأطر')

    def test_downstream_locked_single_section_before_control_plan(self):
        c = self._company_with_intake(cr='7171710001')
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertContains(resp, 'المراحل اللاحقة غير متاحة قبل اعتماد النطاق وإنشاء خطة الضوابط')
        # The four detailed downstream cards must NOT render before the control plan exists.
        self.assertNotContains(resp, 'الجاهزية · Readiness')

    def test_welcome_flag_wording_is_deemphasized(self):
        c = self._company(cr='7272720001')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('زر الترحيب فقط', body)
        self.assertIn('لا تعكس تقدّم رحلة الامتثال', body)

    def test_journey_isolation_between_companies(self):
        # Company A has a full control plan; Company B (viewed) has only intake -> B shows locked.
        from compliance.models import (CompanyIntakeProfile, Framework, FrameworkVersion,
                                        CompanyFrameworkScope, Control, Domain,
                                        ControlApplicabilityResult)
        a = self._company_with_intake(cr='7373730001')
        fw = Framework.objects.create(code='NCAZ', name='NCA')
        fv = FrameworkVersion.objects.create(code='NCA-ECC-2-2024', framework=fw, version_label='ECC')
        dom = Domain.objects.create(framework=fw, code='D', name='D')
        sc = CompanyFrameworkScope.objects.create(company=a, framework_version=fv, status='approved')
        ctrl = Control.objects.create(framework=fw, framework_version=fv, domain=dom,
                                      control_id='E-1', title='t', description='d')
        ControlApplicabilityResult.objects.create(company=a, framework_scope=sc, control=ctrl,
                                                   decision='applicable')
        b = self._company(cr='7474740001')
        CompanyIntakeProfile.objects.create(company=b, uses_cloud_services=True)
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[b.id]))
        # B's page must reflect B only: no control plan, downstream locked.
        self.assertFalse(resp.context['journey']['control_plan_generated'])
        self.assertEqual(resp.context['journey']['generated_controls'], 0)
        self.assertContains(resp, 'المراحل اللاحقة غير متاحة')

    def test_auditor_cannot_access_company_detail(self):
        c = self._company(cr='6464640002')
        u, _p = _auditor(status='active')
        self.client.force_login(u)
        self.assertEqual(self.client.get(
            reverse('platform_admin:company_detail', args=[c.id])).status_code, 403)


class CRMCompanyFollowUpTests(TestCase):
    """Phase 8D-3E-CRM-C — internal CRM notes / follow-up status / activity timeline."""

    def _staff(self, email='crmc@x.com', superuser=False):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True, is_superuser=superuser)

    def _company(self, cr='8181818181', name='FollowUp Co'):
        return Company.objects.create(name=name, cr_number=cr, sector='technology',
                                      size='small', contact_email='fu@co.example')

    def _company_user(self, c, email='fuuser@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        company=c, role='company_admin')

    def _note_url(self, c):
        return reverse('platform_admin:add_note', args=[c.id])

    def _status_url(self, c):
        return reverse('platform_admin:update_status', args=[c.id])

    def _detail_url(self, c):
        return reverse('platform_admin:company_detail', args=[c.id])

    # ---- permissions ----
    def test_anonymous_cannot_add_note(self):
        c = self._company()
        r = self.client.post(self._note_url(c), {'text': 'x'})
        self.assertIn(r.status_code, (302, 403))

    def test_company_user_cannot_add_note_or_status(self):
        c = self._company()
        cu = self._company_user(c)
        self.client.force_login(cu)
        self.assertEqual(self.client.post(self._note_url(c), {'text': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(self._status_url(c), {'crm_status': 'active'}).status_code, 403)

    def test_auditor_cannot_add_note(self):
        c = self._company()
        au = User.objects.create_user(username='fuau@x.com', email='fuau@x.com',
                                      password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=au, full_name='A', status='active')
        self.client.force_login(au)
        self.assertEqual(self.client.post(self._note_url(c), {'text': 'x'}).status_code, 403)

    def test_staff_can_access_detail_no_500_empty(self):
        c = self._company()
        self.client.force_login(self._staff())
        resp = self.client.get(self._detail_url(c))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'لا توجد ملاحظات داخلية بعد')
        self.assertContains(resp, 'لا يوجد نشاط داخلي بعد')

    # ---- notes ----
    def test_staff_can_add_note_and_it_appears(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._note_url(c), {'text': 'Called the customer about onboarding.'})
        from auditors.models import CompanyCRMNote
        self.assertTrue(CompanyCRMNote.objects.filter(company=c).exists())
        body = self.client.get(self._detail_url(c)).content.decode()
        self.assertIn('Called the customer about onboarding.', body)

    def test_note_text_required(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._note_url(c), {'text': '   '})
        from auditors.models import CompanyCRMNote
        self.assertFalse(CompanyCRMNote.objects.filter(company=c).exists())

    def test_note_writes_audit_log(self):
        from core.models import AuditLog
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._note_url(c), {'text': 'audit me'})
        log = AuditLog.objects.filter(action='crm_note_added').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('company_id'), c.id)

    def test_notes_not_visible_in_company_portal(self):
        c = self._company()
        cu = self._company_user(c)
        from auditors.crm_services import add_company_note
        add_company_note(self._staff(), c, 'SECRET-INTERNAL-NOTE')
        self.client.force_login(cu)
        for name in ('compliance:classification', 'dashboard:main'):
            body = self.client.get(reverse(name), follow=True).content.decode()
            self.assertNotIn('SECRET-INTERNAL-NOTE', body)

    def test_notes_not_visible_in_auditor_portal(self):
        c = self._company()
        au = User.objects.create_user(username='fuaud2@x.com', email='fuaud2@x.com',
                                      password='longenough12', role='auditor')
        p = AuditorProfile.objects.create(user=au, full_name='A', status='active')
        a = AuditorAssignment.objects.create(company=c, auditor=p, status='accepted')
        from auditors.crm_services import add_company_note
        add_company_note(self._staff(), c, 'SECRET-INTERNAL-NOTE-2')
        self.client.force_login(au)
        body = self.client.get(reverse('auditors:assignment_detail', args=[a.id])).content.decode()
        self.assertNotIn('SECRET-INTERNAL-NOTE-2', body)

    # ---- status ----
    def test_staff_can_update_status(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._status_url(c), {'crm_status': 'needs_follow_up', 'reason': 'awaiting docs'})
        from auditors.models import CompanyCRMProfile
        self.assertEqual(CompanyCRMProfile.objects.get(company=c).crm_status, 'needs_follow_up')

    def test_invalid_status_rejected(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._status_url(c), {'crm_status': 'not_a_status'})
        from auditors.models import CompanyCRMProfile
        self.assertFalse(CompanyCRMProfile.objects.filter(company=c, crm_status='not_a_status').exists())

    def test_status_appears_on_detail_and_list(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._status_url(c), {'crm_status': 'blocked'})
        detail = self.client.get(self._detail_url(c)).content.decode()
        self.assertIn('محظورة', detail)   # detail page shows the Arabic CRM-status label
        listing = self.client.get(reverse('platform_admin:companies_list')).content.decode()
        self.assertIn('محظورة', listing)   # list page now shows the Arabic CRM-status label

    def test_status_change_writes_audit_log(self):
        from core.models import AuditLog
        c = self._company()
        self.client.force_login(self._staff())
        self.client.post(self._status_url(c), {'crm_status': 'active'})
        log = AuditLog.objects.filter(action='crm_status_changed').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('new_status'), 'active')
        self.assertEqual(log.metadata.get('company_id'), c.id)

    def test_assigned_staff_and_follow_up_date(self):
        c = self._company()
        staff = self._staff()
        assignee = self._staff(email='assignee@x.com')
        self.client.force_login(staff)
        self.client.post(self._status_url(c), {'crm_status': 'onboarding',
                                               'assigned_staff_id': assignee.id,
                                               'next_follow_up_date': '2026-08-15'})
        from auditors.models import CompanyCRMProfile
        prof = CompanyCRMProfile.objects.get(company=c)
        self.assertEqual(prof.assigned_staff_id, assignee.id)
        self.assertEqual(str(prof.next_follow_up_date), '2026-08-15')

    def test_status_does_not_change_company_compliance(self):
        c = self._company()
        before_status = c.status
        self.client.force_login(self._staff())
        self.client.post(self._status_url(c), {'crm_status': 'inactive'})
        c.refresh_from_db()
        self.assertEqual(c.status, before_status)  # company.status (compliance) untouched

    # ---- timeline ----
    def test_timeline_shows_note_status_and_link_events(self):
        c = self._company()
        u = User.objects.create_user(username='tlfree@x.com', email='tlfree@x.com',
                                     password='longenough12', role='company_admin')
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(reverse('platform_admin:link_user', args=[c.id]),
                         {'user_id': u.id, 'reason': 'r'})
        self.client.post(self._status_url(c), {'crm_status': 'active'})
        self.client.post(self._note_url(c), {'text': 'timeline note'})
        from auditors.crm_services import get_company_activity_timeline
        actions = [e['action'] for e in get_company_activity_timeline(c)]
        self.assertIn('crm_link_user', actions)
        self.assertIn('crm_status_changed', actions)
        self.assertIn('crm_note_added', actions)
        body = self.client.get(self._detail_url(c)).content.decode()
        self.assertIn('سجل النشاط الداخلي', body)

    def test_timeline_scoped_to_company(self):
        c1 = self._company(cr='8282828282', name='C1')
        c2 = self._company(cr='8383838383', name='C2')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:add_note', args=[c1.id]), {'text': 'only c1'})
        from auditors.crm_services import get_company_activity_timeline
        self.assertEqual(len(get_company_activity_timeline(c2)), 0)  # no cross-company leakage

    # ---- safety ----
    def test_no_unsafe_wording_on_detail(self):
        c = self._company()
        self.client.force_login(self._staff())
        body = self.client.get(self._detail_url(c)).content.decode()
        self.assertIn('حالة المتابعة', body)
        self.assertIn('ملاحظات داخلية', body)
        for w in ('معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك', 'اعتماد حكومي',
                  'certified by NCA', 'official accreditation', 'government accredited',
                  'official certification'):
            self.assertNotIn(w, body)


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


class AuditorSelectionFlowTests(TestCase):
    """UAT-COMPANY-AUDITOR-SELECTION-ACCEPTANCE-FLOW-A — company selects auditor -> pending ->
    auditor accepts/rejects -> accepted assignment. Reuses the existing AuditorAssignment."""

    def test_company_sees_only_active_available_auditors(self):
        from auditors.services import list_available_auditors
        _, ap = _auditor(status='active')
        _, pending = _auditor(status='pending_review')
        _, unavail = _auditor(status='active', available=False)
        ids = set(list_available_auditors().values_list('id', flat=True))
        self.assertIn(ap.id, ids)
        self.assertNotIn(pending.id, ids)
        self.assertNotIn(unavail.id, ids)

    def test_company_can_request_active_auditor(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        _, ap = _auditor(status='active')
        a, created = create_assignment(c, ap)
        self.assertTrue(created)
        self.assertEqual(a.status, 'requested')

    def test_cannot_request_inactive_auditor(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        _, pending = _auditor(status='pending_review')
        a, created = create_assignment(c, pending)
        self.assertFalse(created)
        self.assertIsNone(a)

    def test_no_duplicate_active_request_for_company(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        _, ap = _auditor(status='active')
        _, ap2 = _auditor(status='active')
        create_assignment(c, ap)
        _, created2 = create_assignment(c, ap2)     # company already has an active request
        self.assertFalse(created2)

    def test_auditor_sees_request_others_do_not(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        create_assignment(c, ap)
        self.client.force_login(u)
        body = self.client.get(reverse('auditors:dashboard')).content.decode()
        self.assertIn('طلبات مراجعة بانتظار موافقتك', body)
        self.assertIn(c.cr_number, body)                 # request visible to this auditor
        u2, _ap2 = _auditor(status='active')
        self.client.force_login(u2)
        body2 = self.client.get(reverse('auditors:dashboard')).content.decode()
        self.assertNotIn(c.cr_number, body2)             # not to another auditor

    def test_auditor_accept_makes_company_assigned(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap)
        self.client.force_login(u)
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]), {'action': 'accept'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'accepted')
        self.assertEqual(a.responded_by, u)

    def test_auditor_reject_requires_reason_then_rejects(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap)
        self.client.force_login(u)
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]), {'action': 'reject'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'requested')          # blocked without a reason
        self.client.post(reverse('auditors:assignment_respond', args=[a.id]),
                         {'action': 'reject', 'reason': 'خارج نطاق تخصّصي'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'rejected')
        self.assertEqual(a.response_note, 'خارج نطاق تخصّصي')

    def test_company_can_reselect_after_reject(self):
        from auditors.services import create_assignment, respond_to_assignment
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap)
        respond_to_assignment(a, 'reject', note='خارج النطاق', responder=u)
        _, ap2 = _auditor(status='active')
        a2, created = create_assignment(c, ap2)          # no active -> allowed again
        self.assertTrue(created)
        self.assertEqual(a2.status, 'requested')

    def test_company_can_cancel_pending(self):
        from auditors.services import create_assignment
        c, cu = _company_user(subscribe=True)
        _, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap, requested_by=cu)
        self.client.force_login(cu)
        self.client.post(reverse('auditors:cancel_assignment', args=[a.id]))
        a.refresh_from_db()
        self.assertEqual(a.status, 'cancelled')

    def test_auditor_cannot_open_non_accepted_company(self):
        # A requested (not accepted) assignment must not grant review-file access.
        from auditors.services import create_assignment, auditor_can_view_company_context
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap)   # requested
        self.assertFalse(auditor_can_view_company_context(a))

    def test_admin_sees_auditor_requests_on_company_page(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        _, ap = _auditor(status='active')
        create_assignment(c, ap)
        staff = User.objects.create_user(username='sel_admin@x.com', email='sel_admin@x.com',
                                         password='longenough12', role='admin', is_staff=True)
        self.client.force_login(staff)
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('طلبات المدققين', body)
        self.assertIn(ap.full_name, body)


class CompanyStepperAuditorSelectionTests(TestCase):
    """The company workflow stepper reflects the auditor-selection request state."""

    def _stage(self, company):
        from compliance.workflow_stepper import build_company_workflow_stepper
        st = build_company_workflow_stepper(company)
        return next(s for s in st['stages'] if s['key'] == 'auditor_selection')

    def test_no_request_shows_choose_auditor(self):
        c, _fv, _s = _company_with_assessments()
        s = self._stage(c)
        self.assertNotEqual(s['status'], 'completed')          # not done until accepted
        self.assertEqual(s['action_label'], 'اختر مدققاً')

    def test_pending_shows_waiting_for_approval(self):
        from auditors.services import create_assignment
        c, _fv, _s = _company_with_assessments()
        _, ap = _auditor(status='active')
        create_assignment(c, ap)
        s = self._stage(c)
        self.assertEqual(s['status'], 'current')
        self.assertEqual(s['action_label'], 'بانتظار موافقة المدقق')

    def test_accepted_marks_selection_completed(self):
        from auditors.services import create_assignment, respond_to_assignment
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = create_assignment(c, ap)
        respond_to_assignment(a, 'accept', responder=u)
        s = self._stage(c)
        self.assertEqual(s['status'], 'completed')


class CompanyDetailUIRedesignTests(TestCase):
    """CYBERTRUST-PLATFORM-ADMIN-COMPANY-DETAIL-UI-REDESIGN-A — the platform-admin
    company-detail page is a CRM dashboard: header + badges + stat cards + in-page
    navigation, with all existing POST forms and permissions unchanged. UI-only."""

    def _staff(self, email='uiredesign_admin@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def _company(self, cr='9191919191', name='UI Redesign Co'):
        return Company.objects.create(name=name, cr_number=cr, sector='technology',
                                      size='small', contact_email='ui@co.example')

    def _url(self, c):
        return reverse('platform_admin:company_detail', args=[c.id])

    # 1) header + company name
    def test_page_shows_header_and_company_name(self):
        c = self._company()
        self.client.force_login(self._staff())
        resp = self.client.get(self._url(c))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, c.name)
        self.assertContains(resp, 'نظرة عامة')

    # 2) status / subscription / email badges
    def test_page_shows_status_badges(self):
        c = self._company(cr='9191910002')
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        self.assertIn('بريد غير موثّق', body)      # email badge (unverified company)
        self.assertIn('مخاطر:', body)               # risk badge
        self.assertIn('لا مدقق مسند', body)         # auditor badge

    # 3) in-page navigation anchors
    def test_page_shows_internal_navigation(self):
        c = self._company(cr='9191910003')
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        for anchor in ('#admin-journey', '#overview', '#journey', '#auditor', '#evidence',
                       '#billing', '#users', '#followup', '#log'):
            self.assertIn('href="%s"' % anchor, body)

    # 4) compliance journey stepper
    def test_page_shows_journey_stepper(self):
        c = self._company(cr='9191910004')
        self.client.force_login(self._staff())
        resp = self.client.get(self._url(c))
        self.assertContains(resp, 'رحلة الامتثال')
        self.assertContains(resp, 'الإجراء التالي:')
        self.assertContains(resp, 'ملخص رحلة الامتثال')

    # 5) evidence summary (counts only, no evidence content)
    def test_page_shows_evidence_summary_counts_only(self):
        c = self._company(cr='9191910005')
        self.client.force_login(self._staff())
        resp = self.client.get(self._url(c))
        self.assertContains(resp, 'الأدلة والجاهزية')
        # counts-only disclaimer present; never render actual evidence file content.
        self.assertContains(resp, 'ولا يُعرض محتوى الأدلة')

    # 6) subscription & payment section
    def test_page_shows_subscription_and_payment(self):
        c = self._company(cr='9191910006')
        self.client.force_login(self._staff())
        resp = self.client.get(self._url(c))
        self.assertContains(resp, 'الاشتراك والدفع')
        self.assertContains(resp, 'ميزات الخطة')

    # 7) add-manual-payment button for staff
    def test_page_shows_add_manual_payment_for_staff(self):
        c = self._company(cr='9191910007')
        self.client.force_login(self._staff())
        self.assertContains(self.client.get(self._url(c)), 'إضافة دفعة يدوية')

    # 8) manual-payments table when a payment exists
    def test_page_shows_manual_payments_table(self):
        from billing import subscription_services as bsvc
        c = self._company(cr='9191910008')
        bsvc.add_manual_payment(c, bsvc.get_plan('basic'), '499', reference='WIRE-1', note='n')
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        self.assertIn('الدفعات اليدوية', body)
        self.assertIn('WIRE-1', body)
        self.assertIn('بانتظار التأكيد', body)

    # 9) Arabic confirmation message (no English leak) on activation
    def test_activation_message_is_arabic_only(self):
        from billing import subscription_services as bsvc
        c = self._company(cr='9191910009')
        bsvc.add_manual_payment(c, bsvc.get_plan('basic'), '499', note='n')
        self.client.force_login(self._staff())
        resp = self.client.post(reverse('platform_admin:subscription_action', args=[c.id]),
                                {'action': 'activate', 'reason': 'confirmed offline'}, follow=True)
        self.assertContains(resp, 'تم تفعيل الاشتراك وتأكيد الدفع اليدوي')
        self.assertNotContains(resp, 'Subscription activated and manual payment confirmed')

    # 10) no unwanted English enum leaks on the Arabic page
    def test_no_unwanted_english_enum_on_page(self):
        from billing import subscription_services as bsvc
        c = self._company(cr='9191910010')
        bsvc.start_trial(c, bsvc.get_plan('basic'))
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        self.assertNotIn('Subscription activated and manual payment confirmed', body)
        # subscription / company / CRM status rendered in Arabic (not the raw enum label)
        self.assertNotIn('>Trial<', body)
        self.assertNotIn('>Active<', body)
        self.assertNotIn('>Registered<', body)

    # 11) tables are wrapped for responsive horizontal scroll
    def test_tables_have_responsive_wrapper(self):
        from billing import subscription_services as bsvc
        c = self._company(cr='9191910011')
        bsvc.add_manual_payment(c, bsvc.get_plan('basic'), '499', note='n')
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        self.assertIn('overflow-x-auto', body)

    # 12) existing action forms still present and unchanged (activate/cancel/manual add/confirm)
    def test_existing_post_forms_intact(self):
        from billing import subscription_services as bsvc
        c = self._company(cr='9191910012')
        # An unlinked user so the link-account form renders too.
        User.objects.create_user(username='uilink@x.com', email='uilink@x.com',
                                 password='longenough12', role='company_admin')
        bsvc.add_manual_payment(c, bsvc.get_plan('basic'), '499', note='n')
        self.client.force_login(self._staff())
        body = self.client.get(self._url(c)).content.decode()
        self.assertIn(reverse('platform_admin:subscription_action', args=[c.id]), body)
        self.assertIn(reverse('platform_admin:add_manual_payment', args=[c.id]), body)
        self.assertIn(reverse('platform_admin:link_user', args=[c.id]), body)
        self.assertIn(reverse('platform_admin:add_note', args=[c.id]), body)
        self.assertIn(reverse('platform_admin:update_status', args=[c.id]), body)
        p = c.payments.filter(provider='manual').first()
        self.assertIn(reverse('platform_admin:confirm_manual_payment', args=[c.id, p.id]), body)
        self.assertIn(reverse('platform_admin:reject_manual_payment', args=[c.id, p.id]), body)
        # Every POST form on the page is CSRF-protected (>= the action forms above).
        self.assertGreaterEqual(body.count('csrfmiddlewaretoken'), 8)

    # 13) permissions unchanged: company user is denied
    def test_company_user_cannot_access(self):
        c = self._company(cr='9191910013')
        u = User.objects.create_user(username='uicu@x.com', email='uicu@x.com',
                                     password='longenough12', role='company_admin', company=c)
        self.client.force_login(u)
        self.assertEqual(self.client.get(self._url(c)).status_code, 403)


class PlatformAdminJourneyTests(TestCase):
    """UAT-PLATFORM-ADMIN-JOURNEY-COMPLETE-UX-LOGIC-A — admin operational journey,
    admin-initiated auditor engagement, and the global auditor-requests page."""

    def _staff(self, email='pajourney_admin@x.com'):
        existing = User.objects.filter(email=email).first()
        if existing is not None:
            return existing
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def _detail(self, c):
        return reverse('platform_admin:company_detail', args=[c.id])

    # ---------- admin journey stepper + next best action ----------
    def test_company_detail_shows_admin_journey_and_next_action(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        resp = self.client.get(self._detail(c))
        self.assertContains(resp, 'مسار إدارة ملف الشركة')
        self.assertContains(resp, 'الإجراء التالي المقترح')
        self.assertContains(resp, 'المدقق')
        j = resp.context['admin_journey']
        keys = [s['key'] for s in j['steps']]
        self.assertEqual(len(keys), 12)
        self.assertIn('auditor_selection', keys)
        self.assertIn('readiness_report', keys)

    def test_auditor_selection_actionable_when_no_auditor(self):
        # The journey is linear (auditor_selection may be gated behind subscription),
        # but the admin can ALWAYS act on the engagement when there is no active auditor.
        from auditors.crm_services import admin_company_journey, admin_auditor_engagement
        c, _fv, _s = _company_with_assessments()
        j = admin_company_journey(c)
        step = next(s for s in j['steps'] if s['key'] == 'auditor_selection')
        self.assertIn(step['status'], ('needs_action', 'locked'))   # never 'completed' with no auditor
        self.assertNotEqual(step['status'], 'completed')
        self.assertTrue(admin_auditor_engagement(c)['can_assign'])

    def test_assign_auditor_button_shown_when_no_auditor(self):
        c, _fv, _s = _company_with_assessments()
        _u, _ap = _auditor(status='active')
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn(reverse('platform_admin:assign_auditor', args=[c.id]), body)

    # ---------- admin assigns an auditor ----------
    def test_admin_can_assign_active_auditor(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:assign_auditor', args=[c.id]),
                         {'auditor_id': ap.id, 'reason': 'assigned by ops'})
        a = AuditorAssignment.objects.filter(company=c, auditor=ap).first()
        self.assertIsNotNone(a)
        self.assertEqual(a.status, 'requested')          # pending until auditor accepts

    def test_admin_cannot_assign_inactive_auditor(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:assign_auditor', args=[c.id]),
                         {'auditor_id': ap.id})
        self.assertFalse(AuditorAssignment.objects.filter(company=c).exists())

    def test_admin_assign_source_is_admin(self):
        from auditors.crm_services import admin_auditor_engagement
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(reverse('platform_admin:assign_auditor', args=[c.id]), {'auditor_id': ap.id})
        eng = admin_auditor_engagement(c)
        self.assertEqual(eng['source'], 'admin')
        self.assertEqual(eng['status'], 'requested')

    def test_cannot_create_two_active_assignments(self):
        c, _fv, _s = _company_with_assessments()
        _u1, ap1 = _auditor(status='active')
        _u2, ap2 = _auditor(status='active')
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(reverse('platform_admin:assign_auditor', args=[c.id]), {'auditor_id': ap1.id})
        self.client.post(reverse('platform_admin:assign_auditor', args=[c.id]), {'auditor_id': ap2.id})
        self.assertEqual(AuditorAssignment.objects.filter(
            company=c, status__in=AuditorAssignment.ACTIVE_STATUSES).count(), 1)

    def test_admin_assign_requires_post(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        self.assertEqual(self.client.get(
            reverse('platform_admin:assign_auditor', args=[c.id])).status_code, 405)

    # ---------- auditor accepts / rejects an admin request ----------
    def test_accepted_shows_in_engagement(self):
        from auditors.crm_services import admin_auditor_engagement
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = services.create_assignment(c, ap, requested_by=self._staff())
        services.respond_to_assignment(a, 'accept', responder=u)
        eng = admin_auditor_engagement(c)
        self.assertTrue(eng['accepted'])
        self.assertEqual(eng['status'], 'accepted')

    def test_rejected_allows_reassignment(self):
        from auditors.crm_services import admin_auditor_engagement
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = services.create_assignment(c, ap, requested_by=self._staff())
        services.respond_to_assignment(a, 'reject', note='not available', responder=u)
        eng = admin_auditor_engagement(c)
        self.assertTrue(eng['can_assign'])               # can pick another
        self.assertIsNotNone(eng['last_rejected'])

    # ---------- admin cancels a pending request ----------
    def test_admin_cancel_request_requires_reason(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        services.create_assignment(c, ap, requested_by=self._staff())
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:cancel_auditor_request', args=[c.id]), {'reason': ''})
        self.assertTrue(AuditorAssignment.objects.filter(company=c, status='requested').exists())

    def test_admin_cancel_request_cancels_pending(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        services.create_assignment(c, ap, requested_by=self._staff())
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:cancel_auditor_request', args=[c.id]),
                         {'reason': 'wrong auditor'})
        self.assertFalse(AuditorAssignment.objects.filter(company=c, status='requested').exists())
        self.assertTrue(AuditorAssignment.objects.filter(company=c, status='cancelled').exists())

    # ---------- global auditor requests page ----------
    def test_auditor_requests_page_lists_requests(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        services.create_assignment(c, ap, requested_by=self._staff())
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:auditor_requests'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'طلبات المدققين')
        self.assertContains(resp, ap.full_name)

    def test_dashboard_shows_operational_queues(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertContains(resp, 'قوائم تحتاج إجراء إداري')
        self.assertIn('companies_no_auditor', resp.context['queues'])

    # ---------- permissions ----------
    def test_company_user_cannot_assign_auditor(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        cu = _journey_user(c)
        self.client.force_login(cu)
        self.assertEqual(self.client.post(
            reverse('platform_admin:assign_auditor', args=[c.id]), {'auditor_id': ap.id}).status_code, 403)
        self.assertFalse(AuditorAssignment.objects.filter(company=c).exists())

    def test_auditor_cannot_access_requests_page(self):
        u, _ap = _auditor(status='active')
        self.client.force_login(u)
        self.assertEqual(self.client.get(
            reverse('platform_admin:auditor_requests')).status_code, 403)

    def test_manual_payment_still_works_after_changes(self):
        from billing import subscription_services as bsvc
        from billing.subscription_access import company_has_active_subscription
        c, _fv, _s = _company_with_assessments()
        p = bsvc.add_manual_payment(c, bsvc.get_plan('basic'), '499', note='n')
        bsvc.confirm_manual_payment(p, reason='wire confirmed')
        self.assertTrue(company_has_active_subscription(c))


class PlatformAdminJourneyFixBTests(TestCase):
    """UAT-PLATFORM-ADMIN-JOURNEY-UX-LOGIC-FIX-B — quick actions surfaced, Arabic-only
    labels, and clear source-aware auditor engagement on the admin company page."""

    def _staff(self, email='fixb_admin@x.com'):
        existing = User.objects.filter(email=email).first()
        return existing or User.objects.create_user(
            username=email, email=email, password='longenough12', role='admin', is_staff=True)

    def _detail(self, c):
        return reverse('platform_admin:company_detail', args=[c.id])

    def _feat_plan(self):
        from billing.tests import _feat_plan, _activate
        return _feat_plan, _activate

    # ---------- quick actions surfaced at the top ----------
    def test_quick_actions_present(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        for label in ('العودة للشركات', 'عرض رحلة الامتثال', 'إضافة ملاحظة',
                      'إدارة المدقق', 'إضافة دفعة يدوية'):
            self.assertIn(label, body)

    def test_next_best_action_card_present(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        self.assertContains(self.client.get(self._detail(c)), 'الإجراء التالي المقترح')

    # ---------- Arabic feature labels (no raw English codes) ----------
    def test_feature_codes_are_arabic(self):
        from billing.tests import _feat_plan, _activate
        c, _fv, _s = _company_with_assessments()
        _activate(c, _feat_plan())
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('رفع الأدلة', body)               # evidence_upload -> Arabic
        self.assertNotIn('evidence_upload', body)
        self.assertNotIn('auditor_review', body)
        self.assertNotIn('gap_analysis', body)

    # ---------- Arabic activity labels (no bilingual English suffix) ----------
    def test_activity_labels_are_arabic_only(self):
        c, _fv, _s = _company_with_assessments()
        staff = self._staff()
        self.client.force_login(staff)
        self.client.post(reverse('platform_admin:update_status', args=[c.id]),
                         {'crm_status': 'active'})
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('تغيير حالة المتابعة', body)
        self.assertNotIn('Follow-up status changed', body)
        self.assertNotIn('User linked', body)

    # ---------- source-aware pending phrasing ----------
    def test_admin_assignment_shows_admin_source_phrasing(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        staff = self._staff()
        services.create_assignment(c, ap, requested_by=staff)
        self.client.force_login(staff)
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('إسناد إداري بانتظار موافقة المدقق', body)

    def test_company_request_shows_company_source_phrasing(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        cu = _journey_user(c)
        services.create_assignment(c, ap, requested_by=cu)     # company-initiated
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('طلب من الشركة بانتظار موافقة المدقق', body)

    def test_accepted_shows_change_not_supported_note(self):
        c, _fv, _s = _company_with_assessments()
        u, ap = _auditor(status='active')
        a, _ = services.create_assignment(c, ap, requested_by=self._staff())
        services.respond_to_assignment(a, 'accept', responder=u)
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('تغيير المدقق بعد القبول غير مدعوم', body)

    # ---------- operational status: disclaimer + subscription ----------
    def test_operational_status_has_disclaimer_and_subscription(self):
        c, _fv, _s = _company_with_assessments()
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('عرض تشغيلي داخلي، لا يمثل قرار امتثال أو اعتماداً رسمياً', body)
        self.assertIn('الحالة التشغيلية', body)

    # ---------- next action routes to a section ----------
    def test_next_action_routes_to_a_section(self):
        from auditors.crm_services import admin_company_journey
        c, _fv, _s = _company_with_assessments()
        na = admin_company_journey(c)['next_action']
        self.assertTrue(na['anchor'].startswith('#'))    # always routes somewhere

    # ---------- auditor-requests page still renders with next-action column ----------
    def test_requests_page_has_next_action_column(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        services.create_assignment(c, ap, requested_by=self._staff())
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:auditor_requests')).content.decode()
        self.assertIn('الإجراء التالي', body)
        self.assertIn('بانتظار موافقة المدقق', body)


class PlatformAdminPolishCTests(TestCase):
    """UAT-PLATFORM-ADMIN-JOURNEY-UX-POLISH-C — final Arabic/RTL + responsive polish
    on the platform-admin company journey pages."""

    def _staff(self, email='polishc_admin@x.com'):
        existing = User.objects.filter(email=email).first()
        return existing or User.objects.create_user(
            username=email, email=email, password='longenough12', role='admin', is_staff=True)

    def _company(self, cr='9393930001', sector='technology', size='micro'):
        return Company.objects.create(name='Polish Co', cr_number=cr, sector=sector,
                                      size=size, contact_email='polish@co.example')

    def _detail(self, c):
        return reverse('platform_admin:company_detail', args=[c.id])

    # A1 — navigation labels are Arabic-only (English nav labels removed)
    def test_nav_labels_are_arabic_only(self):
        c = self._company()
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        for ar in ('نظرة عامة', 'الشركات', 'المدققون', 'حسابات غير مرتبطة', 'تسجيل الخروج'):
            self.assertIn(ar, body)
        for en in ('· Overview', '· Auditors', '· Logout', 'Internal operations console'):
            self.assertNotIn(en, body)

    # A3 — company sector/size render Arabic labels for known choices
    def test_sector_and_size_are_arabic(self):
        c = self._company(sector='technology', size='micro')
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('تقنية المعلومات', body)
        self.assertIn('صغيرة جدًا (1-9 موظفين)', body)
        self.assertNotIn('>Technology<', body)
        self.assertNotIn('Micro (1-9 employees)', body)

    # C1 — auditor assignment button text is unambiguous
    def test_assign_button_says_send_request(self):
        c = self._company()
        _u, _ap = _auditor(status='active')
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('إرسال طلب إسناد مدقق', body)
        self.assertIn('ولا يصبح المدقق مسندًا إلا بعد القبول', body)

    # C3 — empty state when no auditor request
    def test_empty_state_when_no_auditor_request(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.assertContains(self.client.get(self._detail(c)),
                            'لا توجد طلبات مدققين لهذه الشركة بعد')

    # C4 — admin-created pending request shows source wording
    def test_admin_pending_request_shows_source(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        staff = self._staff()
        services.create_assignment(c, ap, requested_by=staff)
        self.client.force_login(staff)
        self.assertContains(self.client.get(self._detail(c)),
                            'إسناد إداري بانتظار موافقة المدقق')

    # B1 — linked users use overflow-safe wrapping (no inner horizontal scroll table)
    def test_linked_users_use_wrapping_markup(self):
        c = self._company()
        User.objects.create_user(username='lu_polish@x.com', email='lu_polish@x.com',
                                 password='longenough12', role='company_admin', company=c)
        self.client.force_login(self._staff())
        body = self.client.get(self._detail(c)).content.decode()
        self.assertIn('break-all', body)          # emails wrap instead of overflowing

    # D1 — date field carries an Arabic format hint
    def test_date_hint_present(self):
        c = self._company()
        self.client.force_login(self._staff())
        self.assertContains(self.client.get(self._detail(c)), 'صيغة التاريخ: YYYY-MM-DD')

    # permissions unchanged
    def test_company_user_denied(self):
        c = self._company()
        u = User.objects.create_user(username='cu_polish@x.com', email='cu_polish@x.com',
                                     password='longenough12', role='company_admin', company=c)
        self.client.force_login(u)
        self.assertEqual(self.client.get(self._detail(c)).status_code, 403)


class PlatformAdminPolishDTests(TestCase):
    """UAT-PLATFORM-ADMIN-FINAL-ARABIC-RTL-POLISH-D — the general platform-admin list
    pages (dashboard/companies/auditors/requests/unlinked) render Arabic/RTL only."""

    def _staff(self, email='polishd_admin@x.com'):
        existing = User.objects.filter(email=email).first()
        return existing or User.objects.create_user(
            username=email, email=email, password='longenough12', role='admin', is_staff=True)

    def _company(self, cr='9494940001', sector='technology'):
        return Company.objects.create(name='PolishD Co', cr_number=cr, sector=sector,
                                      size='small', contact_email='pd@co.example')

    # ---- dashboard ----
    def test_dashboard_is_arabic(self):
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:dashboard')).content.decode()
        for ar in ('لوحة إدارة المنصة', 'روابط سريعة', 'صحة بيانات الأطر الرسمية',
                   'قوائم تحتاج إجراء إداري'):
            self.assertIn(ar, body)
        for en in ('Official data health', 'Quick links', '· Companies', '· Users',
                   '· Frameworks', '· Controls'):
            self.assertNotIn(en, body)

    # ---- companies list ----
    def test_companies_list_is_arabic(self):
        c = self._company(sector='technology')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:companies_list')).content.decode()
        self.assertIn('الشركات', body)
        self.assertIn('تفاصيل', body)
        self.assertIn('تقنية المعلومات', body)          # sector Arabic
        for en in ('· Company', '· Status', '· Sector', '· Created', 'تفاصيل · View',
                   'No companies registered yet'):
            self.assertNotIn(en, body)

    # ---- auditors list ----
    def test_auditors_list_is_arabic(self):
        _u, _ap = _auditor(status='pending_review')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:auditor_list')).content.decode()
        self.assertIn('قيد المراجعة', body)              # filter + status Arabic
        self.assertIn('مراجعة', body)                    # action link
        self.assertNotIn('Pending Review', body)
        self.assertNotIn('>Suspended<', body)

    # ---- auditor requests ----
    def test_auditor_requests_is_arabic(self):
        c, _fv, _s = _company_with_assessments()
        _u, ap = _auditor(status='active')
        staff = self._staff()
        services.create_assignment(c, ap, requested_by=staff)
        self.client.force_login(staff)
        body = self.client.get(reverse('platform_admin:auditor_requests')).content.decode()
        self.assertIn('أسندته الإدارة', body)            # source Arabic
        self.assertIn('بانتظار موافقة المدقق', body)     # next action Arabic
        self.assertIn('الإجراء التالي', body)
        self.assertIn('مصدر الطلب', body)

    # ---- unlinked accounts ----
    def test_unlinked_accounts_is_arabic(self):
        User.objects.create_user(username='pdorphan@x.com', email='pdorphan@x.com',
                                 password='longenough12', role='company_admin')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:unlinked_accounts')).content.decode()
        self.assertIn('حسابات غير مرتبطة', body)
        self.assertNotIn('· Email', body)
        self.assertNotIn('· Role', body)

    def test_unlinked_empty_state_arabic(self):
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:unlinked_accounts')).content.decode()
        self.assertIn('لا توجد حسابات غير مرتبطة حاليًا', body)
        self.assertNotIn('No unlinked accounts currently', body)

    # ---- permissions unchanged ----
    def test_company_user_denied_on_admin_pages(self):
        c = self._company(cr='9494940099')
        u = User.objects.create_user(username='pdcu@x.com', email='pdcu@x.com',
                                     password='longenough12', role='company_admin', company=c)
        self.client.force_login(u)
        for name in ('dashboard', 'companies_list', 'auditor_list', 'auditor_requests',
                     'unlinked_accounts'):
            self.assertEqual(self.client.get(reverse('platform_admin:%s' % name)).status_code, 403)

    def test_auditor_user_denied_on_admin_pages(self):
        u, _ap = _auditor(status='active')
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('platform_admin:auditor_requests')).status_code, 403)
