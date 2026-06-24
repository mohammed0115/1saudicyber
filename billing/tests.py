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
            'sector': 'technology', 'size': 'small', 'target_nca': 'on'})

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
                'password': 'longenough12', 'target_nca': 'on'})
        self.assertEqual(resp.status_code, 302)
