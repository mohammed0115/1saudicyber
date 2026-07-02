"""Phase 4B — subscription model/service + report-gating tests."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import User, Company
from billing.models import CompanySubscription
from billing.subscription_access import (
    get_company_subscription, ensure_company_subscription, company_has_active_subscription,
    activate_company_subscription, expire_company_subscription,
    can_view_full_reports, can_export_reports,
)

# Reuse the proven compliance fixtures.
from compliance.tests import _company_with_assessments, _journey_user, _company_with_submission


def _sub(company, status='active', days=30, exports=True):
    now = timezone.now()
    return CompanySubscription.objects.create(
        company=company, status=status, plan_name='P',
        starts_at=now, ends_at=(now + timedelta(days=days)) if days else None,
        report_exports_allowed=exports)


class SubscriptionModelServiceTests(TestCase):
    def setUp(self):
        self.c = Company.objects.create(name='SubCo', cr_number='2020202020',
                                        sector='technology', size='small', contact_email='s@x.com')

    def test_subscription_can_be_created(self):
        s = _sub(self.c)
        self.assertEqual(CompanySubscription.objects.count(), 1)
        self.assertTrue(s.is_active())

    def test_active_subscription_allows_reports(self):
        _sub(self.c, status='active')
        self.assertTrue(company_has_active_subscription(self.c))
        self.assertTrue(can_view_full_reports(self.c))
        self.assertTrue(can_export_reports(self.c))

    def test_trial_subscription_allows_reports(self):
        _sub(self.c, status='trial')
        self.assertTrue(company_has_active_subscription(self.c))
        self.assertTrue(can_view_full_reports(self.c))

    def test_expired_subscription_blocks_reports(self):
        # Past end date OR expired status both block.
        _sub(self.c, status='active', days=-1)
        self.assertFalse(company_has_active_subscription(self.c))
        expire_company_subscription(self.c)
        self.assertFalse(can_view_full_reports(self.c))

    def test_suspended_subscription_blocks_reports(self):
        _sub(self.c, status='suspended')
        self.assertFalse(company_has_active_subscription(self.c))
        self.assertFalse(can_export_reports(self.c))

    def test_inactive_subscription_blocks_reports(self):
        # No subscription at all, and an explicit inactive row.
        self.assertFalse(company_has_active_subscription(self.c))
        ensure_company_subscription(self.c)
        self.assertEqual(get_company_subscription(self.c).status, 'inactive')
        self.assertFalse(can_view_full_reports(self.c))

    def test_exports_flag_can_block_export_only(self):
        _sub(self.c, status='active', exports=False)
        self.assertTrue(can_view_full_reports(self.c))   # view allowed
        self.assertFalse(can_export_reports(self.c))     # export disabled

    def test_subscription_activation_command_creates_or_updates_subscription(self):
        out = StringIO()
        call_command('activate_company_subscription', '--company-id', str(self.c.id),
                     '--plan-name', 'UAT Plan', '--days', '15', stdout=out)
        s = get_company_subscription(self.c)
        self.assertIsNotNone(s)
        self.assertEqual(s.status, 'active')
        self.assertEqual(s.plan_name, 'UAT Plan')
        # Idempotent re-run updates the same row (no duplicate).
        call_command('activate_company_subscription', '--company-id', str(self.c.id),
                     '--plan-name', 'UAT Plan 2', '--days', '30', stdout=StringIO())
        self.assertEqual(CompanySubscription.objects.filter(company=self.c).count(), 1)
        self.assertEqual(get_company_subscription(self.c).plan_name, 'UAT Plan 2')


SUB_MSG = 'تفعيل الاشتراك مطلوب'


class ReportGatingTests(TestCase):
    def setUp(self):
        self.c, self.fv, self.scope = _company_with_assessments()
        self.user = _journey_user(self.c)
        self.client.force_login(self.user)

    def _subscribe(self):
        activate_company_subscription(self.c, 'Plan', days=30)

    def test_reports_index_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('compliance:reports_index'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_unsubscribed_company_sees_subscription_required_message(self):
        resp = self.client.get(reverse('compliance:report_executive_summary'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, SUB_MSG)

    def test_unsubscribed_company_cannot_export_csv(self):
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertNotEqual(resp.get('Content-Type'), 'text/csv')
        self.assertNotIn(b'control_id', resp.content)
        self.assertContains(resp, SUB_MSG)

    def test_unsubscribed_company_cannot_export_xlsx(self):
        resp = self.client.get(reverse('compliance:export_evidence_matrix_xlsx'))
        self.assertNotEqual(resp.content[:2], b'PK')  # not an xlsx file
        self.assertContains(resp, SUB_MSG)

    def test_subscribed_company_can_view_executive_summary(self):
        self._subscribe()
        resp = self.client.get(reverse('compliance:report_executive_summary'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, SUB_MSG)
        self.assertContains(resp, 'غير المُراجَعة')  # the real report content

    def test_subscribed_company_can_view_gap_analysis(self):
        self._subscribe()
        resp = self.client.get(reverse('compliance:report_gap_analysis'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, SUB_MSG)

    def test_subscribed_company_can_view_evidence_matrix(self):
        self._subscribe()
        resp = self.client.get(reverse('compliance:report_evidence_matrix'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, SUB_MSG)

    def test_subscribed_company_can_export_csv(self):
        self._subscribe()
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn(b'control_id', resp.content)

    def test_subscribed_company_can_export_xlsx(self):
        self._subscribe()
        resp = self.client.get(reverse('compliance:export_evidence_matrix_xlsx'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content[:2], b'PK')

    def test_report_gating_is_tenant_scoped(self):
        # A subscribed -> can export; B (separate, unsubscribed) -> cannot.
        self._subscribe()
        self.assertEqual(self.client.get(reverse('compliance:export_evidence_matrix_csv'))['Content-Type'], 'text/csv')
        b, bfv, bscope = _company_with_assessments('SABIC-CYBERTRUST-1-0')
        buser = _journey_user(b)
        self.client.force_login(buser)
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertContains(resp, SUB_MSG)
        self.assertNotIn(b'control_id', resp.content)

    def test_staff_or_superuser_bypass_rule_if_implemented(self):
        # Documented rule: NO staff bypass. Staff are gated by their OWN company's
        # subscription exactly like company users (no special report bypass).
        staff = _journey_user(self.c, email='staff-gate@x.com', is_staff=True)
        self.client.force_login(staff)
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertContains(resp, SUB_MSG)  # gated despite is_staff
        activate_company_subscription(self.c, 'Plan', days=30)
        resp2 = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertEqual(resp2['Content-Type'], 'text/csv')


class ReportSafetyTests(TestCase):
    """Subscription gating must not change report calculations or safety rules."""
    def setUp(self):
        from compliance.models import ControlAssessment
        self.c, self.fv, self.scope = _company_with_assessments()
        self.A = ControlAssessment

    def test_report_calculations_unchanged_by_subscription(self):
        from compliance.reporting import build_executive_summary
        before = build_executive_summary(self.c)['counts']
        activate_company_subscription(self.c, 'Plan', days=30)
        after = build_executive_summary(self.c)['counts']
        self.assertEqual(before, after)

    def test_unreviewed_not_counted_as_compliant(self):
        from compliance.reporting import build_executive_summary
        s = build_executive_summary(self.c)  # all not_reviewed
        self.assertEqual(s['counts']['compliant'], 0)
        self.assertEqual(s['compliance_percentage'], 0.0)

    def test_ai_not_used_as_final_decision(self):
        from compliance.evidence_analysis import analyze_evidence_submission
        c, item, sub = _company_with_submission()
        before = self.A.objects.filter(company=c, status='compliant').count()
        analyze_evidence_submission(sub, apply=True)
        self.assertEqual(self.A.objects.filter(company=c, status='compliant').count(), before)

    def test_legacy_334_not_used_as_report_source(self):
        from compliance.reporting import build_framework_gap_analysis
        from compliance.models import Control, Domain
        fw = self.fv.framework
        Control.objects.create(framework=fw, domain=Domain.objects.filter(framework=fw).first(),
                               control_id='LEG-4B', title='legacy', description='d')
        gap = build_framework_gap_analysis(self.c)
        ids = [g['control_id'] for f in gap for g in f['gaps']]
        self.assertNotIn('LEG-4B', ids)

    def test_no_companycontrol_created_by_subscription(self):
        from compliance.models import CompanyControl
        before = CompanyControl.objects.count()
        activate_company_subscription(self.c, 'Plan', days=30)
        expire_company_subscription(self.c)
        self.assertEqual(CompanyControl.objects.count(), before)


class SubscriptionUxTests(TestCase):
    def setUp(self):
        self.c, self.fv, self.scope = _company_with_assessments()
        self.user = _journey_user(self.c)
        self.client.force_login(self.user)

    def test_subscription_required_page_renders(self):
        resp = self.client.get(reverse('compliance:report_executive_summary'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, SUB_MSG)
        self.assertContains(resp, 'العودة إلى لوحة الرحلة')

    def test_report_export_buttons_have_loading_state(self):
        activate_company_subscription(self.c, 'Plan', days=30)
        resp = self.client.get(reverse('compliance:report_evidence_matrix'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ تجهيز ملف CSV')

    def test_dashboard_shows_subscription_status(self):
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'التقارير تتطلب اشتراكًا')
        activate_company_subscription(self.c, 'Plan', days=30)
        resp2 = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp2, 'التقارير مفعّلة')


class Phase4BBackwardCompatTests(TestCase):
    def setUp(self):
        call_command('seed_framework_versions', stdout=StringIO())

    def _register(self):
        return self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bc4b@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC Co', 'cr_number': '1414141414',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

    def test_company_registration_still_works(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='1414141414').exists())

    def test_onboarding_still_works(self):
        self._register()
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_intake_still_works(self):
        self._register()
        self.assertEqual(self.client.get(reverse('compliance:intake')).status_code, 200)

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

    def test_auditor_assessment_still_works(self):
        from compliance.control_assessment import update_assessment_from_auditor_input
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        u = _journey_user(c, email='aud4b@x.com', is_staff=True)
        update_assessment_from_auditor_input(a, {'status': 'compliant'}, u)
        a.refresh_from_db()
        self.assertEqual(a.status, 'compliant')

    def test_old_registration_still_works(self):
        with mock.patch('core.views.classify_company', return_value={'error': 'skip'}):
            resp = self.client.post(reverse('core:register'), {
                'company_name': 'Legacy4B', 'cr_number': '1515151515', 'sector': 'technology',
                'size': 'small', 'first_name': 'A', 'last_name': 'B', 'email': 'leg4b@x.com',
                'password': 'longenough12', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(resp.status_code, 302)


# ============================================================
# Phase 8I-SUBSCRIPTION-A — Plans + Subscription Foundation
# ============================================================
from compliance.tests import _company
from billing.models import Plan, Payment, CompanySubscription
from billing import subscription_services as bsvc
from billing.subscription_access import company_has_active_subscription


class SubscriptionFoundationServiceTests(TestCase):
    def _plan(self, code='basic'):
        return bsvc.get_plan(code)

    def test_starter_plans_seeded(self):
        for code in ('trial', 'basic', 'professional', 'enterprise'):
            self.assertTrue(Plan.objects.filter(code=code, is_active=True).exists(), code)

    def test_start_trial(self):
        c = _company()
        sub = bsvc.start_trial(c, self._plan('professional'))
        self.assertEqual(sub.status, 'trial')
        self.assertTrue(company_has_active_subscription(c))
        self.assertIsNotNone(sub.trial_ends_at)

    def test_single_subscription_no_duplicates(self):
        c = _company()
        bsvc.start_trial(c, self._plan('trial'))
        bsvc.create_pending_subscription(c, self._plan('basic'))
        self.assertEqual(CompanySubscription.objects.filter(company=c).count(), 1)

    def test_create_pending_subscription(self):
        c = _company()
        sub, pay = bsvc.create_pending_subscription(c, self._plan('basic'))
        self.assertEqual(sub.status, 'pending_payment')
        self.assertEqual(pay.status, 'pending')
        self.assertEqual(pay.provider, 'manual')
        self.assertEqual(pay.provider_payment_id, '')   # no Moyasar id yet
        self.assertFalse(company_has_active_subscription(c))

    def test_activate_subscription(self):
        c = _company()
        sub = bsvc.get_current_subscription(c)
        bsvc.activate_subscription(sub, reason='paid offline')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'active')
        self.assertTrue(company_has_active_subscription(c))

    def test_cancel_subscription(self):
        c = _company()
        sub = bsvc.start_trial(c, self._plan('basic'))
        bsvc.cancel_subscription(sub, reason='customer request')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'cancelled')
        self.assertIsNotNone(sub.cancelled_at)
        self.assertFalse(company_has_active_subscription(c))

    def test_expire_subscription(self):
        c = _company()
        sub = bsvc.start_trial(c, self._plan('basic'))
        bsvc.expire_subscription(sub, reason='ended')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'expired')
        self.assertFalse(company_has_active_subscription(c))

    def test_create_manual_payment(self):
        c = _company()
        sub = bsvc.get_current_subscription(c)
        pay = bsvc.create_manual_payment(sub, 100, reference='ref1')
        self.assertEqual(pay.status, 'pending')
        self.assertEqual(pay.company_id, c.id)

    def test_mark_payment_paid_activates_pending(self):
        c = _company()
        sub, pay = bsvc.create_pending_subscription(c, self._plan('basic'))
        bsvc.mark_payment_paid(pay)
        pay.refresh_from_db(); sub.refresh_from_db()
        self.assertEqual(pay.status, 'paid')
        self.assertIsNotNone(pay.paid_at)
        self.assertEqual(sub.status, 'active')

    def test_active_helper(self):
        c = _company()
        self.assertFalse(company_has_active_subscription(c))
        bsvc.start_trial(c, self._plan('basic'))
        self.assertTrue(company_has_active_subscription(c))

    def test_feature_enabled_helper(self):
        c = _company()
        bsvc.start_trial(c, self._plan('enterprise'))
        self.assertTrue(bsvc.subscription_feature_enabled(c, 'auditor_review_enabled'))
        c2 = _company()
        bsvc.start_trial(c2, self._plan('basic'))
        self.assertFalse(bsvc.subscription_feature_enabled(c2, 'auditor_review_enabled'))

    def test_feature_disabled_without_subscription(self):
        c = _company()
        self.assertFalse(bsvc.subscription_feature_enabled(c, 'pdf_export_enabled'))
        self.assertFalse(bsvc.can_access_feature(c, 'pdf_export_enabled'))

    def test_limit_helper(self):
        c = _company()
        bsvc.start_trial(c, self._plan('professional'))
        self.assertEqual(bsvc.subscription_limit_value(c, 'max_frameworks'), 3)

    def test_expired_not_active(self):
        c = _company()
        sub = bsvc.start_trial(c, self._plan('basic'))
        bsvc.expire_subscription(sub)
        self.assertFalse(company_has_active_subscription(c))

    def test_pending_not_active(self):
        c = _company()
        bsvc.create_pending_subscription(c, self._plan('basic'))
        self.assertFalse(company_has_active_subscription(c))

    def test_lifecycle_writes_audit(self):
        from core.models import AuditLog
        c = _company()
        u = _journey_user(c, email='subaudit@x.com')
        bsvc.start_trial(c, self._plan('basic'), actor=u)
        self.assertTrue(AuditLog.objects.filter(action='subscription_trial_started').exists())

    def test_no_card_fields_on_payment(self):
        fields = {f.name for f in Payment._meta.get_fields()}
        for banned in ('card', 'card_number', 'pan', 'cvv', 'cvc', 'card_holder'):
            self.assertNotIn(banned, fields)


class BillingViewTests(TestCase):
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def test_anonymous_redirected(self):
        r = self.client.get(reverse('billing:home'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.url)

    def test_company_user_can_view(self):
        c = _company()
        self._login(c, 'bvv@x.com')
        resp = self.client.get(reverse('billing:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Current subscription')
        self.assertContains(resp, 'Available plans')

    def test_unlinked_user_safe_no_company(self):
        u = User.objects.create_user(username='bvorph@x.com', email='bvorph@x.com',
                                     password='longenough12', role='company_admin')
        self.client.force_login(u)
        self.assertContains(self.client.get(reverse('billing:home')), 'not linked to a company', status_code=200)

    def test_auditor_denied(self):
        from auditors.models import AuditorProfile
        au = User.objects.create_user(username='bvaud@x.com', email='bvaud@x.com',
                                      password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=au, full_name='A', status='active')
        self.client.force_login(au)
        self.assertContains(self.client.get(reverse('billing:home')), 'Auditor account', status_code=200)

    def test_staff_without_company_routed_to_crm(self):
        st = User.objects.create_user(username='bvstaff@x.com', email='bvstaff@x.com',
                                      password='longenough12', role='admin', is_staff=True)
        self.client.force_login(st)
        self.assertContains(self.client.get(reverse('billing:home')), 'Get Solution CRM', status_code=200)

    def test_start_trial_requires_post(self):
        c = _company()
        self._login(c, 'bvtp@x.com')
        self.assertEqual(self.client.get(reverse('billing:start_trial')).status_code, 405)

    def test_start_trial_creates_trial(self):
        c = _company()
        self._login(c, 'bvt@x.com')
        self.client.post(reverse('billing:start_trial'), {'plan_code': 'trial'})
        self.assertTrue(company_has_active_subscription(c))

    def test_select_plan_creates_pending(self):
        c = _company()
        self._login(c, 'bvsp@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        sub = bsvc.get_current_subscription(c)
        self.assertEqual(sub.status, 'pending_payment')
        self.assertTrue(Payment.objects.filter(company=c, status='pending').exists())

    def test_no_moyasar_checkout_link(self):
        c = _company()
        self._login(c, 'bvmoy@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertNotIn('api.moyasar.com', body)
        self.assertNotIn('https://checkout', body)
        pay = Payment.objects.filter(company=c).first()
        self.assertEqual(pay.provider, 'manual')
        self.assertEqual(pay.provider_payment_id, '')

    def test_billing_page_safe_disclaimer(self):
        c = _company()
        self._login(c, 'bvsafe@x.com')
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('not an official certification', body.lower())
        for w in ('معتمد من NCA', 'اعتماد حكومي', 'certified by NCA', 'official accreditation',
                  'government accredited'):
            self.assertNotIn(w, body)


class BillingCRMTests(TestCase):
    def _staff(self, email='billstaff@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def test_crm_detail_shows_subscription_summary(self):
        c = _company()
        bsvc.start_trial(c, bsvc.get_plan('basic'))
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('platform_admin:company_detail', args=[c.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Subscription')

    def test_staff_can_activate_subscription(self):
        c = _company()
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:subscription_action', args=[c.id]),
                         {'action': 'activate', 'reason': 'offline payment'})
        self.assertTrue(company_has_active_subscription(c))

    def test_activate_requires_reason(self):
        c = _company()
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:subscription_action', args=[c.id]),
                         {'action': 'activate', 'reason': ''})
        self.assertFalse(company_has_active_subscription(c))

    def test_subscription_action_requires_post(self):
        c = _company()
        self.client.force_login(self._staff())
        self.assertEqual(self.client.get(
            reverse('platform_admin:subscription_action', args=[c.id])).status_code, 405)

    def test_non_staff_cannot_access_subscription_action(self):
        c = _company()
        self.client.force_login(_journey_user(c, email='billns@x.com'))
        resp = self.client.post(reverse('platform_admin:subscription_action', args=[c.id]),
                                {'action': 'activate', 'reason': 'x'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(company_has_active_subscription(c))

    def test_crm_action_writes_audit(self):
        from core.models import AuditLog
        c = _company()
        self.client.force_login(self._staff())
        self.client.post(reverse('platform_admin:subscription_action', args=[c.id]),
                         {'action': 'activate', 'reason': 'r'})
        self.assertTrue(AuditLog.objects.filter(action='subscription_activated').exists())


# ============================================================
# Phase 8I-B — Moyasar Sandbox Checkout (UI/flow only; NO activation)
# ============================================================
from django.test import override_settings
from billing import moyasar as bmoyasar

_PK = 'pk_test_sandboxkey123'          # safe sandbox publishable key (fake)
_LIVE_PK = 'pk_live_shouldnevershow'   # a live key must never reach the browser
_SECRET = 'sk_test_secretmustnotleak'  # secret key must never reach the browser


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET,
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarConfigTests(TestCase):
    def test_provider_and_mode(self):
        self.assertTrue(bmoyasar.is_moyasar_provider())
        self.assertEqual(bmoyasar.moyasar_mode(), 'sandbox')

    def test_publishable_key_exposed_only_when_sandbox(self):
        self.assertEqual(bmoyasar.publishable_key_for_template(), _PK)
        self.assertTrue(bmoyasar.is_configured())

    @override_settings(MOYASAR_PUBLISHABLE_KEY=_LIVE_PK)
    def test_live_publishable_key_not_exposed(self):
        self.assertEqual(bmoyasar.publishable_key_for_template(), '')
        self.assertFalse(bmoyasar.is_configured())

    @override_settings(MOYASAR_PUBLISHABLE_KEY='')
    def test_missing_key_not_configured(self):
        self.assertEqual(bmoyasar.publishable_key_for_template(), '')
        self.assertFalse(bmoyasar.is_configured())

    def test_checkout_metadata_has_no_secrets(self):
        c = _company()
        sub, pay = bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        meta = bmoyasar.checkout_metadata(pay)
        self.assertEqual(meta['internal_payment_id'], str(pay.id))
        self.assertEqual(meta['plan_code'], 'basic')
        blob = str(meta)
        self.assertNotIn(_SECRET, blob)
        self.assertNotIn('sk_', blob)


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET,
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarCheckoutFlowTests(TestCase):
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def test_select_plan_creates_moyasar_payment_and_redirects_to_checkout(self):
        c = _company()
        self._login(c, 'mflow1@x.com')
        resp = self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        self.assertEqual(pay.provider, 'moyasar')
        self.assertEqual(pay.status, 'pending')
        self.assertRedirects(resp, reverse('billing:checkout', args=[pay.id]),
                             fetch_redirect_response=False)
        sub = bsvc.get_current_subscription(c)
        self.assertEqual(sub.status, 'pending_payment')

    def test_checkout_page_renders_form_and_publishable_key(self):
        c = _company()
        self._login(c, 'mflow2@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        body = self.client.get(reverse('billing:checkout', args=[pay.id])).content.decode()
        self.assertIn('mysr-form', body)
        self.assertIn(_PK, body)
        self.assertIn('Sandbox', body)

    def test_secret_key_never_in_checkout_html(self):
        c = _company()
        self._login(c, 'mflow3@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        body = self.client.get(reverse('billing:checkout', args=[pay.id])).content.decode()
        self.assertNotIn(_SECRET, body)
        self.assertNotIn('sk_test_', body)
        self.assertNotIn('sk_live_', body)

    def test_checkout_tenant_scoped_other_company_denied(self):
        c1 = _company(); c2 = _company()
        u2 = _journey_user(c2, email='mflow4b@x.com')
        self._login(c1, 'mflow4a@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c1)
        self.client.force_login(u2)
        resp = self.client.get(reverse('billing:checkout', args=[pay.id]))
        self.assertRedirects(resp, reverse('billing:home'), fetch_redirect_response=False)

    def test_checkout_requires_pending_payment(self):
        c = _company()
        self._login(c, 'mflow5@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        pay.status = 'paid'; pay.save()
        resp = self.client.get(reverse('billing:checkout', args=[pay.id]))
        self.assertRedirects(resp, reverse('billing:home'), fetch_redirect_response=False)

    def test_checkout_started_audited(self):
        from core.models import AuditLog
        c = _company()
        self._login(c, 'mflow6@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        self.client.get(reverse('billing:checkout', args=[pay.id]))
        self.assertTrue(AuditLog.objects.filter(action='moyasar_checkout_started').exists())

    def test_billing_home_shows_pay_button(self):
        c = _company()
        self._login(c, 'mflow7@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('Pay with Moyasar Sandbox', body)


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY='', MOYASAR_SECRET_KEY=_SECRET,
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarNotConfiguredTests(TestCase):
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def test_checkout_shows_not_configured_message(self):
        c = _company()
        self._login(c, 'mnc1@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        resp = self.client.get(reverse('billing:checkout', args=[pay.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('not configured yet', resp.content.decode())

    def test_checkout_does_not_crash_without_key(self):
        c = _company()
        self._login(c, 'mnc2@x.com')
        self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        pay = Payment.objects.get(company=c)
        self.assertEqual(self.client.get(
            reverse('billing:checkout', args=[pay.id])).status_code, 200)


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET,
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarCallbackTests(TestCase):
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def _pending(self, c):
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        return Payment.objects.get(company=c)

    def test_callback_records_but_does_not_activate(self):
        c = _company()
        self._login(c, 'mcb1@x.com')
        pay = self._pending(c)
        resp = self.client.get(reverse('billing:moyasar_callback'),
                               {'ipid': pay.id, 'id': 'moyasar_pay_123', 'status': 'paid'})
        self.assertRedirects(resp, reverse('billing:home'), fetch_redirect_response=False)
        pay.refresh_from_db()
        self.assertEqual(pay.provider_payment_id, 'moyasar_pay_123')
        self.assertEqual(pay.status, 'pending')            # NOT paid
        sub = bsvc.get_current_subscription(c)
        self.assertEqual(sub.status, 'pending_payment')    # NOT activated
        self.assertFalse(company_has_active_subscription(c))

    def test_callback_shows_pending_verification_message(self):
        c = _company()
        self._login(c, 'mcb2@x.com')
        pay = self._pending(c)
        resp = self.client.get(reverse('billing:moyasar_callback'),
                               {'ipid': pay.id, 'id': 'x1', 'status': 'paid'}, follow=True)
        self.assertContains(resp, 'Subscription will be activated after verification')

    def test_callback_failed_marks_payment_failed(self):
        c = _company()
        self._login(c, 'mcb3@x.com')
        pay = self._pending(c)
        self.client.get(reverse('billing:moyasar_callback'),
                        {'ipid': pay.id, 'id': 'x2', 'status': 'failed'})
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'failed')
        self.assertFalse(company_has_active_subscription(c))

    def test_callback_cancelled_marks_payment_cancelled(self):
        c = _company()
        self._login(c, 'mcb4@x.com')
        pay = self._pending(c)
        self.client.get(reverse('billing:moyasar_callback'),
                        {'ipid': pay.id, 'id': 'x3', 'status': 'cancelled'})
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'cancelled')

    def test_callback_forged_other_company_no_effect(self):
        c1 = _company(); c2 = _company()
        pay1 = self._pending(c1)
        self._login(c2, 'mcb5@x.com')   # attacker in c2 forges callback for c1's payment
        resp = self.client.get(reverse('billing:moyasar_callback'),
                               {'ipid': pay1.id, 'id': 'evil', 'status': 'paid'})
        self.assertRedirects(resp, reverse('billing:home'), fetch_redirect_response=False)
        pay1.refresh_from_db()
        self.assertEqual(pay1.provider_payment_id, '')      # untouched
        self.assertFalse(company_has_active_subscription(c1))

    def test_callback_missing_ipid_no_500(self):
        c = _company()
        self._login(c, 'mcb6@x.com')
        resp = self.client.get(reverse('billing:moyasar_callback'), {'status': 'paid'})
        self.assertEqual(resp.status_code, 302)

    def test_callback_invalid_ipid_no_500(self):
        c = _company()
        self._login(c, 'mcb7@x.com')
        resp = self.client.get(reverse('billing:moyasar_callback'),
                               {'ipid': 'notanumber', 'id': 'x', 'status': 'paid'})
        self.assertEqual(resp.status_code, 302)

    def test_callback_audited(self):
        from core.models import AuditLog
        c = _company()
        self._login(c, 'mcb8@x.com')
        pay = self._pending(c)
        self.client.get(reverse('billing:moyasar_callback'),
                        {'ipid': pay.id, 'id': 'x9', 'status': 'paid'})
        self.assertTrue(AuditLog.objects.filter(action='moyasar_callback_received').exists())


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET)
class MoyasarCRMTests(TestCase):
    def _staff(self, email='mcrmstaff@x.com'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True)

    def test_crm_shows_provider_and_pending_moyasar(self):
        from auditors import crm_services as crm
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        summary = crm.company_subscription_summary(c)
        self.assertEqual(summary['pending_moyasar_payments'], 1)
        self.assertEqual(summary['last_payment_provider'], 'Moyasar')

    def test_crm_detail_page_no_secret(self):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        self.client.force_login(self._staff())
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('Pending Moyasar', body)
        self.assertNotIn(_SECRET, body)


class MoyasarSafetyTests(TestCase):
    """Provider defaults keep manual behaviour intact (no override_settings here)."""
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def test_default_provider_is_manual(self):
        self.assertFalse(bmoyasar.is_moyasar_provider())

    def test_manual_flow_unchanged_when_provider_manual(self):
        c = _company()
        self._login(c, 'msafe1@x.com')
        resp = self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
        self.assertRedirects(resp, reverse('billing:home'), fetch_redirect_response=False)
        pay = Payment.objects.get(company=c)
        self.assertEqual(pay.provider, 'manual')

    def test_checkout_safe_disclaimer(self):
        with override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_PUBLISHABLE_KEY=_PK,
                               PUBLIC_BASE_URL='http://localhost:8000'):
            c = _company()
            self._login(c, 'msafe2@x.com')
            self.client.post(reverse('billing:select_plan'), {'plan_code': 'basic'})
            pay = Payment.objects.get(company=c)
            body = self.client.get(reverse('billing:checkout', args=[pay.id])).content.decode()
            self.assertIn('not an official certification', body.lower())
            for w in ('certified by NCA', 'government accredited', 'official accreditation'):
                self.assertNotIn(w, body)


# ============================================================
# Phase 8I-C — Moyasar Webhook + Payment Verification
# ============================================================
import json as _json
from billing import verification as bverify


def _moyasar_payload(payment, status='paid', amount=None, currency=None, ppid='moy_pay_abc',
                     wrap=False, metadata=None):
    """Build a Moyasar-shaped payment payload matching (or deliberately not) a Payment."""
    if amount is None:
        amount = int((payment.amount or 0) * 100)
    if currency is None:
        currency = payment.currency
    if metadata is None:
        metadata = {'internal_payment_id': str(payment.id), 'company_id': str(payment.company_id),
                    'subscription_id': str(payment.subscription_id or ''), 'plan_code': 'basic'}
    obj = {'id': ppid, 'status': status, 'amount': amount, 'currency': currency, 'metadata': metadata}
    return {'type': 'payment_%s' % status, 'data': obj} if wrap else obj


def _ok_fetch(payload):
    return {'ok': True, 'status_code': 200, 'payload': payload, 'error': ''}


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET,
                   MOYASAR_WEBHOOK_SECRET='', PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarVerificationServiceTests(TestCase):
    def _pending(self, c=None, ppid=''):
        c = c or _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c)
        if ppid:
            pay.provider_payment_id = ppid; pay.save()
        return c, pay

    def test_status_mapping(self):
        self.assertEqual(bverify.map_moyasar_status('paid'), 'paid')
        self.assertEqual(bverify.map_moyasar_status('captured'), 'paid')
        self.assertEqual(bverify.map_moyasar_status('failed'), 'failed')
        self.assertEqual(bverify.map_moyasar_status('refunded'), 'refunded')
        self.assertEqual(bverify.map_moyasar_status('voided'), 'cancelled')
        self.assertEqual(bverify.map_moyasar_status('initiated'), 'pending')
        self.assertEqual(bverify.map_moyasar_status('authorized'), 'pending')
        self.assertIsNone(bverify.map_moyasar_status('weird'))

    def test_verified_paid_activates(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, status='paid')
        res = bverify.process_moyasar_payment_result(pay, payload, source='webhook', allow_activation=True)
        pay.refresh_from_db(); sub = bsvc.get_current_subscription(c)
        self.assertTrue(res['activated'])
        self.assertEqual(pay.status, 'paid')
        self.assertIsNotNone(pay.paid_at)
        self.assertEqual(pay.provider_payment_id, 'moy_pay_abc')
        self.assertEqual(sub.status, 'active')
        self.assertTrue(company_has_active_subscription(c))
        self.assertEqual(pay.provider_metadata.get('last_provider_status'), 'paid')

    def test_activation_writes_audit(self):
        from core.models import AuditLog
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=True)
        self.assertTrue(AuditLog.objects.filter(action='subscription_activated_from_moyasar').exists())
        self.assertTrue(AuditLog.objects.filter(action='moyasar_payment_paid').exists())
        self.assertTrue(AuditLog.objects.filter(action='moyasar_payment_verified').exists())

    def test_amount_mismatch_no_activation(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, amount=1)   # wrong amount
        res = bverify.process_moyasar_payment_result(pay, payload, allow_activation=True)
        pay.refresh_from_db()
        self.assertFalse(res['activated'])
        self.assertEqual(res['reason'], 'amount_mismatch')
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))

    def test_currency_mismatch_no_activation(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, currency='USD')
        res = bverify.process_moyasar_payment_result(pay, payload, allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(res['reason'], 'currency_mismatch')
        self.assertEqual(pay.status, 'pending')

    def test_company_metadata_mismatch_no_activation(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, metadata={'internal_payment_id': str(pay.id),
                                                  'company_id': '999999', 'subscription_id': str(pay.subscription_id)})
        res = bverify.process_moyasar_payment_result(pay, payload, allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(res['reason'], 'company_mismatch')
        self.assertFalse(company_has_active_subscription(c))

    def test_payment_metadata_mismatch_no_activation(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, metadata={'internal_payment_id': '424242',
                                                  'company_id': str(pay.company_id)})
        res = bverify.process_moyasar_payment_result(pay, payload, allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(res['reason'], 'payment_metadata_mismatch')
        self.assertEqual(pay.status, 'pending')

    def test_subscription_metadata_mismatch_no_activation(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, metadata={'internal_payment_id': str(pay.id),
                                                  'company_id': str(pay.company_id), 'subscription_id': '888'})
        res = bverify.process_moyasar_payment_result(pay, payload, allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(res['reason'], 'subscription_mismatch')

    def test_already_failed_payment_not_activated(self):
        c, pay = self._pending()
        pay.status = 'failed'; pay.save()
        res = bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=True)
        pay.refresh_from_db()
        self.assertFalse(res['activated'])
        self.assertEqual(pay.status, 'failed')
        self.assertFalse(company_has_active_subscription(c))

    def test_subscription_not_pending_no_activation(self):
        c, pay = self._pending()
        sub = bsvc.get_current_subscription(c); sub.status = 'inactive'; sub.save()
        res = bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=True)
        pay.refresh_from_db()
        self.assertFalse(res['activated'])
        self.assertEqual(pay.status, 'pending')

    def test_not_server_verified_does_not_activate(self):
        c, pay = self._pending()
        res = bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=False)
        pay.refresh_from_db()
        self.assertFalse(res['activated'])
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))

    def test_failed_maps_to_failed(self):
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay, status='failed'), allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'failed')
        self.assertFalse(company_has_active_subscription(c))

    def test_refunded_maps_to_refunded(self):
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay, status='refunded'), allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'refunded')

    def test_voided_maps_to_cancelled(self):
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay, status='voided'), allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'cancelled')

    def test_initiated_keeps_pending(self):
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay, status='initiated'), allow_activation=True)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')

    def test_idempotent_double_paid(self):
        c, pay = self._pending()
        bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=True)
        sub = bsvc.get_current_subscription(c); first_ends = sub.ends_at
        res2 = bverify.process_moyasar_payment_result(pay, _moyasar_payload(pay), allow_activation=True)
        pay.refresh_from_db(); sub.refresh_from_db()
        self.assertEqual(res2['action'], 'already_paid')
        self.assertEqual(pay.status, 'paid')
        self.assertEqual(Payment.objects.filter(company=c).count(), 1)
        self.assertEqual(CompanySubscription.objects.filter(company=c).count(), 1)

    def test_verify_moyasar_payment_fetch_then_activate(self):
        c, pay = self._pending(ppid='moy_verify_1')
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value=_ok_fetch(_moyasar_payload(pay, ppid='moy_verify_1'))):
            res = bverify.verify_moyasar_payment(pay, source='manual')
        pay.refresh_from_db()
        self.assertTrue(res['activated'])
        self.assertEqual(pay.status, 'paid')

    def test_verify_no_provider_id_safe(self):
        c, pay = self._pending()
        res = bverify.verify_moyasar_payment(pay)
        self.assertFalse(res.get('ok'))
        self.assertEqual(res['reason'], 'no_provider_id')


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_MODE='sandbox',
                   MOYASAR_PUBLISHABLE_KEY=_PK, MOYASAR_SECRET_KEY=_SECRET,
                   MOYASAR_WEBHOOK_SECRET='', PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarWebhookEndpointTests(TestCase):
    def _pending(self, ppid='moy_wh_1'):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c)
        pay.provider_payment_id = ppid; pay.save()
        return c, pay

    def _post(self, payload):
        return self.client.post(reverse('billing:moyasar_webhook'),
                                data=_json.dumps(payload), content_type='application/json')

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse('billing:moyasar_webhook')).status_code, 405)

    def test_malformed_json_no_500(self):
        resp = self.client.post(reverse('billing:moyasar_webhook'), data='{not json',
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_missing_payment_id_no_500(self):
        resp = self._post({'type': 'payment_paid', 'data': {'status': 'paid'}})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_provider_id_no_activation(self):
        c, pay = self._pending()
        payload = {'data': {'id': 'does_not_exist', 'status': 'paid', 'amount': 1,
                            'currency': 'SAR', 'metadata': {}}}
        with mock.patch('billing.moyasar.fetch_moyasar_payment') as fetch:
            resp = self._post(payload)
            fetch.assert_not_called()   # no local match -> never even fetch
        self.assertEqual(resp.status_code, 200)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')

    def test_webhook_paid_activates_after_fetch(self):
        c, pay = self._pending(ppid='moy_wh_paid')
        fetched = _moyasar_payload(pay, ppid='moy_wh_paid', status='paid')
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(fetched)):
            resp = self._post(_moyasar_payload(pay, ppid='moy_wh_paid', status='paid', wrap=True))
        self.assertEqual(resp.status_code, 200)
        pay.refresh_from_db(); sub = bsvc.get_current_subscription(c)
        self.assertEqual(pay.status, 'paid')
        self.assertIsNotNone(pay.paid_at)
        self.assertEqual(sub.status, 'active')
        self.assertTrue(company_has_active_subscription(c))

    def test_webhook_fetch_failure_no_activation(self):
        c, pay = self._pending(ppid='moy_wh_fail')
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value={'ok': False, 'error': 'network', 'status_code': 0, 'payload': {}}):
            resp = self._post(_moyasar_payload(pay, ppid='moy_wh_fail', status='paid', wrap=True))
        self.assertEqual(resp.status_code, 200)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')          # fetch failed -> not activated
        self.assertFalse(company_has_active_subscription(c))

    def test_webhook_forged_amount_no_activation(self):
        """Attacker POSTs paid, but the authoritative fetch shows a wrong amount."""
        c, pay = self._pending(ppid='moy_wh_forge')
        forged_fetch = _moyasar_payload(pay, ppid='moy_wh_forge', status='paid', amount=1)
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(forged_fetch)):
            resp = self._post(_moyasar_payload(pay, ppid='moy_wh_forge', status='paid', wrap=True))
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))

    def test_webhook_duplicate_paid_idempotent(self):
        c, pay = self._pending(ppid='moy_wh_dup')
        fetched = _moyasar_payload(pay, ppid='moy_wh_dup', status='paid')
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(fetched)):
            self._post(_moyasar_payload(pay, ppid='moy_wh_dup', status='paid', wrap=True))
            self._post(_moyasar_payload(pay, ppid='moy_wh_dup', status='paid', wrap=True))
        self.assertEqual(Payment.objects.filter(company=c, status='paid').count(), 1)
        self.assertEqual(CompanySubscription.objects.filter(company=c, status='active').count(), 1)

    def test_webhook_duplicate_failed_safe(self):
        c, pay = self._pending(ppid='moy_wh_df')
        fetched = _moyasar_payload(pay, ppid='moy_wh_df', status='failed')
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(fetched)):
            self._post(_moyasar_payload(pay, ppid='moy_wh_df', status='failed', wrap=True))
            self._post(_moyasar_payload(pay, ppid='moy_wh_df', status='failed', wrap=True))
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'failed')
        self.assertFalse(company_has_active_subscription(c))

    def test_webhook_paid_after_active_idempotent(self):
        c, pay = self._pending(ppid='moy_wh_aa')
        fetched = _moyasar_payload(pay, ppid='moy_wh_aa', status='paid')
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(fetched)):
            self._post(_moyasar_payload(pay, ppid='moy_wh_aa', status='paid', wrap=True))
        sub = bsvc.get_current_subscription(c); ends1 = sub.ends_at
        with mock.patch('billing.moyasar.fetch_moyasar_payment', return_value=_ok_fetch(fetched)):
            self._post(_moyasar_payload(pay, ppid='moy_wh_aa', status='paid', wrap=True))
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'active')
        self.assertEqual(sub.ends_at, ends1)   # not extended again

    def test_webhook_writes_received_and_invalid_audit(self):
        from core.models import AuditLog
        c, pay = self._pending()
        self._post({'data': {'status': 'paid'}})   # no id -> invalid
        self.assertTrue(AuditLog.objects.filter(action='moyasar_webhook_received').exists())
        self.assertTrue(AuditLog.objects.filter(action='moyasar_webhook_invalid').exists())


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_PUBLISHABLE_KEY=_PK,
                   MOYASAR_SECRET_KEY='', MOYASAR_WEBHOOK_SECRET='',
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarMissingSecretTests(TestCase):
    def _pending(self, ppid='moy_ns'):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c)
        pay.provider_payment_id = ppid; pay.save()
        return c, pay

    def test_fetch_no_secret_returns_safe(self):
        res = bmoyasar.fetch_moyasar_payment('moy_x')
        self.assertFalse(res['ok'])
        self.assertEqual(res['error'], 'no_secret')

    def test_webhook_without_secret_does_not_activate(self):
        c, pay = self._pending()
        resp = self.client.post(reverse('billing:moyasar_webhook'),
                                data=_json.dumps(_moyasar_payload(pay, ppid='moy_ns', status='paid', wrap=True)),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))

    def test_verify_without_secret_does_not_activate(self):
        c, pay = self._pending()
        res = bverify.verify_moyasar_payment(pay)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_PUBLISHABLE_KEY=_PK,
                   MOYASAR_SECRET_KEY=_SECRET, MOYASAR_WEBHOOK_SECRET='shared_token_123',
                   PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarWebhookSecretTests(TestCase):
    def _pending(self, ppid='moy_ws'):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c)
        pay.provider_payment_id = ppid; pay.save()
        return c, pay

    def test_wrong_secret_rejected_403(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, ppid='moy_ws', status='paid', wrap=True)
        payload['secret_token'] = 'wrong'
        resp = self.client.post(reverse('billing:moyasar_webhook'),
                                data=_json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')

    def test_correct_secret_processed(self):
        c, pay = self._pending()
        payload = _moyasar_payload(pay, ppid='moy_ws', status='paid', wrap=True)
        payload['secret_token'] = 'shared_token_123'
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value=_ok_fetch(_moyasar_payload(pay, ppid='moy_ws', status='paid'))):
            resp = self.client.post(reverse('billing:moyasar_webhook'),
                                    data=_json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'paid')


@override_settings(PAYMENT_PROVIDER='moyasar', MOYASAR_PUBLISHABLE_KEY=_PK,
                   MOYASAR_SECRET_KEY=_SECRET, PUBLIC_BASE_URL='http://localhost:8000')
class MoyasarPhase8ICSecurityUITests(TestCase):
    def _login(self, c, email):
        self.client.force_login(_journey_user(c, email=email))

    def test_secret_never_in_webhook_response(self):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c); pay.provider_payment_id = 'moy_s'; pay.save()
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value=_ok_fetch(_moyasar_payload(pay, ppid='moy_s'))):
            resp = self.client.post(reverse('billing:moyasar_webhook'),
                                    data=_json.dumps(_moyasar_payload(pay, ppid='moy_s', wrap=True)),
                                    content_type='application/json')
        self.assertNotIn(_SECRET, resp.content.decode())

    def test_no_card_fields_on_payment(self):
        fields = {f.name for f in Payment._meta.get_fields()}
        for banned in ('card', 'card_number', 'pan', 'cvv', 'cvc', 'card_holder', 'cardholder'):
            self.assertNotIn(banned, fields)

    def test_billing_waiting_verification_state(self):
        c = _company()
        self._login(c, 'uic1@x.com')
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c); pay.provider_payment_id = 'moy_w'; pay.save()
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('Waiting for payment verification', body)
        self.assertNotIn(_SECRET, body)

    def test_billing_failed_state(self):
        c = _company()
        self._login(c, 'uic2@x.com')
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c); pay.status = 'failed'; pay.save()
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('did not complete', body)

    def test_crm_shows_safe_moyasar_verification(self):
        from auditors import crm_services as crm
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c); pay.provider_payment_id = 'moy_crm'; pay.save()
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value=_ok_fetch(_moyasar_payload(pay, ppid='moy_crm'))):
            bverify.verify_moyasar_payment(pay)
        summary = crm.company_subscription_summary(c)
        self.assertEqual(summary['last_moyasar_status'], 'paid')
        self.assertIsNotNone(summary['last_payment_paid_at'])
        self.assertIn('failed_moyasar_payments', summary)
        self.assertNotIn(_SECRET, str(summary))

    def test_crm_detail_no_secret(self):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        staff = User.objects.create_user(username='uicstaff@x.com', email='uicstaff@x.com',
                                         password='longenough12', role='admin', is_staff=True)
        self.client.force_login(staff)
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('Failed Moyasar', body)
        self.assertNotIn(_SECRET, body)

    def test_callback_still_does_not_activate(self):
        c = _company()
        self._login(c, 'uiccb@x.com')
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c)
        resp = self.client.get(reverse('billing:moyasar_callback'),
                               {'ipid': pay.id, 'id': 'moy_cb', 'status': 'paid'}, follow=True)
        pay.refresh_from_db()
        self.assertEqual(pay.status, 'pending')
        self.assertFalse(company_has_active_subscription(c))
        self.assertContains(resp, 'Subscription will be activated after verification')

    def test_webhook_safe_no_certification_wording(self):
        c = _company()
        bsvc.create_pending_subscription(c, bsvc.get_plan('basic'), provider='moyasar')
        pay = Payment.objects.get(company=c); pay.provider_payment_id = 'moy_sc'; pay.save()
        with mock.patch('billing.moyasar.fetch_moyasar_payment',
                        return_value=_ok_fetch(_moyasar_payload(pay, ppid='moy_sc'))):
            resp = self.client.post(reverse('billing:moyasar_webhook'),
                                    data=_json.dumps(_moyasar_payload(pay, ppid='moy_sc', wrap=True)),
                                    content_type='application/json')
        for w in ('official certification', 'government accredited', 'certified by NCA'):
            self.assertNotIn(w, resp.content.decode())
