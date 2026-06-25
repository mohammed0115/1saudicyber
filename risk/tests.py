"""Phase 5A — Risk Register & Remediation tests."""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.models import User, Company
from risk.models import RiskItem, RemediationTask, severity_for_score
from risk import services

from compliance.tests import _company_with_assessments, _journey_user, _company_with_submission
from auditors.tests import _auditor, _assignment


def _company(name='RiskCo', cr=None):
    n = Company.objects.count() + 1
    return Company.objects.create(name=name, cr_number=cr or f'{4000000000 + n}',
                                  sector='technology', size='small', contact_email=f'r{n}@x.com')


def _risk(company, likelihood=3, impact=3, **kw):
    return RiskItem.objects.create(company=company, title=kw.pop('title', 'Risk'),
                                   likelihood=likelihood, impact=impact, **kw)


class RiskScoringTests(TestCase):
    def test_risk_score_likelihood_times_impact(self):
        r = _risk(_company(), likelihood=4, impact=5)
        self.assertEqual(r.inherent_score, 20)
        self.assertEqual(r.score, 20)

    def test_risk_severity_low_medium_high_critical(self):
        self.assertEqual(severity_for_score(3), 'low')
        self.assertEqual(severity_for_score(9), 'medium')
        self.assertEqual(severity_for_score(16), 'high')
        self.assertEqual(severity_for_score(25), 'critical')
        c = _company()
        self.assertEqual(_risk(c, 1, 2).severity, 'low')
        self.assertEqual(_risk(c, 3, 3).severity, 'medium')
        self.assertEqual(_risk(c, 4, 4).severity, 'high')
        self.assertEqual(_risk(c, 5, 5).severity, 'critical')

    def test_residual_score_optional(self):
        c = _company()
        self.assertIsNone(_risk(c).residual_score)
        r = _risk(c, residual_likelihood=2, residual_impact=2)
        self.assertEqual(r.residual_score, 4)

    def test_remediation_task_defaults(self):
        c = _company()
        t = RemediationTask.objects.create(company=c, risk=_risk(c), title='T')
        self.assertEqual(t.status, 'todo')
        self.assertEqual(t.priority, 'medium')
        self.assertIsNone(t.completed_at)
        t.status = 'done'; t.save()
        self.assertIsNotNone(t.completed_at)


class RiskPermissionTests(TestCase):
    def test_risk_register_requires_login(self):
        resp = self.client.get(reverse('risk:list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_company_user_sees_only_own_risks(self):
        a = _company('A'); b = _company('B', cr='4999999999')
        _risk(a, title='ARisk'); _risk(b, title='BRisk')
        self.client.force_login(_journey_user(a))
        resp = self.client.get(reverse('risk:list'))
        self.assertContains(resp, 'ARisk')
        self.assertNotContains(resp, 'BRisk')

    def test_company_user_cannot_access_other_company_risk(self):
        a = _company('A'); b = _company('B', cr='4999999998')
        br = _risk(b, title='BRisk')
        self.client.force_login(_journey_user(a))
        resp = self.client.get(reverse('risk:detail', args=[br.id]))
        self.assertEqual(resp.status_code, 302)  # tenant-scoped redirect

    def test_staff_can_view_company_risks(self):
        a = _company('A')
        _risk(a, title='StaffSeesThis')
        self.client.force_login(_journey_user(a, is_staff=True))
        self.assertContains(self.client.get(reverse('risk:list')), 'StaffSeesThis')

    def test_assigned_auditor_can_view_assigned_company_risks_readonly(self):
        c, fv, scope = _company_with_assessments()
        _risk(c, title='AuditorReadsThis')
        u, p = _auditor(status='active')
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(reverse('risk:auditor_view', args=[a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AuditorReadsThis')
        self.assertContains(resp, 'للقراءة فقط')

    def test_unassigned_auditor_cannot_view_risks(self):
        c, fv, scope = _company_with_assessments()
        u1, p1 = _auditor(status='active')
        u2, p2 = _auditor(status='active')
        a = _assignment(c, p2, status='accepted')
        self.client.force_login(u1)  # not assigned
        self.assertEqual(self.client.get(reverse('risk:auditor_view', args=[a.id])).status_code, 302)

    def test_pending_auditor_cannot_view_risks(self):
        c, fv, scope = _company_with_assessments()
        u, p = _auditor(status='pending_review')
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('risk:auditor_view', args=[a.id])).status_code, 302)


class RiskCrudTests(TestCase):
    def setUp(self):
        self.c = _company()
        self.user = _journey_user(self.c)
        self.client.force_login(self.user)

    def test_company_user_can_create_manual_risk(self):
        resp = self.client.post(reverse('risk:create'), {
            'title': 'Manual risk', 'description': 'd', 'category': 'access_control',
            'likelihood': 4, 'impact': 4, 'status': 'open', 'owner_name': 'Owner'})
        self.assertEqual(resp.status_code, 302)
        r = RiskItem.objects.get(company=self.c, title='Manual risk')
        self.assertEqual(r.severity, 'high')  # 16
        self.assertEqual(r.created_by, self.user)

    def test_company_user_can_edit_own_risk(self):
        r = _risk(self.c, title='Edit me')
        resp = self.client.post(reverse('risk:edit', args=[r.id]), {
            'title': 'Edited', 'description': '', 'category': 'other',
            'likelihood': 5, 'impact': 5, 'status': 'in_progress', 'owner_name': ''})
        self.assertEqual(resp.status_code, 302)
        r.refresh_from_db()
        self.assertEqual(r.title, 'Edited')
        self.assertEqual(r.severity, 'critical')

    def test_company_user_can_create_remediation_task(self):
        r = _risk(self.c)
        resp = self.client.post(reverse('risk:task_create', args=[r.id]), {
            'title': 'Fix it', 'description': '', 'owner_name': 'Eng',
            'priority': 'high', 'status': 'todo', 'verification_notes': ''})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(RemediationTask.objects.filter(risk=r, title='Fix it').exists())

    def test_company_user_can_update_remediation_task(self):
        r = _risk(self.c)
        t = RemediationTask.objects.create(company=self.c, risk=r, title='T')
        resp = self.client.post(reverse('risk:task_edit', args=[t.id]), {
            'title': 'T', 'description': '', 'owner_name': '', 'priority': 'medium',
            'status': 'done', 'verification_notes': 'verified'})
        self.assertEqual(resp.status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.status, 'done')
        self.assertIsNotNone(t.completed_at)

    def test_mark_risk_mitigated_requires_explicit_action_or_status_update(self):
        r = _risk(self.c, title='Mit')
        # Adding a done task does NOT auto-close the risk.
        RemediationTask.objects.create(company=self.c, risk=r, title='T', status='done')
        r.refresh_from_db()
        self.assertEqual(r.status, 'open')
        # Explicit edit to mitigated is required.
        self.client.post(reverse('risk:edit', args=[r.id]), {
            'title': 'Mit', 'description': '', 'category': 'other',
            'likelihood': 1, 'impact': 1, 'status': 'mitigated', 'owner_name': ''})
        r.refresh_from_db()
        self.assertEqual(r.status, 'mitigated')


class RiskSourceLinkTests(TestCase):
    def test_create_risk_from_control_assessment_link(self):
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        self.client.force_login(_journey_user(c))
        resp = self.client.post(reverse('risk:create') + f'?assessment_id={a.id}', {
            'title': 'From assessment', 'description': '', 'category': 'governance',
            'likelihood': 2, 'impact': 2, 'status': 'open', 'owner_name': ''})
        self.assertEqual(resp.status_code, 302)
        r = RiskItem.objects.get(company=c, title='From assessment')
        self.assertEqual(r.control_assessment_id, a.id)
        self.assertEqual(r.source, 'control_assessment')

    def test_create_risk_from_evidence_analysis_link(self):
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        analyze_evidence_submission(sub, apply=True)
        n = EvidenceAnalysisResult.objects.filter(company=c).first()
        self.client.force_login(_journey_user(c))
        resp = self.client.post(reverse('risk:create') + f'?analysis_id={n.id}', {
            'title': 'From analysis', 'description': '', 'category': 'governance',
            'likelihood': 2, 'impact': 2, 'status': 'open', 'owner_name': ''})
        self.assertEqual(resp.status_code, 302)
        r = RiskItem.objects.get(company=c, title='From analysis')
        self.assertEqual(r.evidence_analysis_result_id, n.id)
        self.assertEqual(r.source, 'evidence_analysis')

    def test_risk_creation_does_not_change_controlassessment(self):
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        before = a.status
        self.client.force_login(_journey_user(c))
        self.client.post(reverse('risk:create') + f'?assessment_id={a.id}', {
            'title': 'X', 'description': '', 'category': 'other',
            'likelihood': 1, 'impact': 1, 'status': 'open', 'owner_name': ''})
        a.refresh_from_db()
        self.assertEqual(a.status, before)

    def test_risk_creation_does_not_make_ai_final_decision(self):
        from compliance.models import ControlAssessment
        c, item, sub = _company_with_submission()
        before = ControlAssessment.objects.filter(company=c, status='compliant').count()
        self.client.force_login(_journey_user(c))
        self.client.post(reverse('risk:create'), {
            'title': 'X', 'description': '', 'category': 'other',
            'likelihood': 1, 'impact': 1, 'status': 'open', 'owner_name': ''})
        self.assertEqual(ControlAssessment.objects.filter(company=c, status='compliant').count(), before)


class RiskUiTests(TestCase):
    def setUp(self):
        self.c = _company()
        self.client.force_login(_journey_user(self.c))

    def test_risk_register_page_arabic_rtl(self):
        resp = self.client.get(reverse('risk:list'))
        self.assertContains(resp, 'dir="rtl"')
        self.assertContains(resp, 'سجل المخاطر')

    def test_risk_dashboard_counts_render(self):
        _risk(self.c, 5, 5, status='open')  # high/critical open
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'سجل المخاطر وخطة المعالجة')
        self.assertContains(resp, 'عالية/حرجة')

    def test_risk_loading_states_present(self):
        resp = self.client.get(reverse('risk:create'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ حفظ الخطر')

    def test_risk_links_visible_from_dashboard_or_reports(self):
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, reverse('risk:list'))

    def test_workflow_stepper_includes_risk_stage_if_added(self):
        from compliance.workflow_stepper import build_company_workflow_stepper
        st = build_company_workflow_stepper(self.c)
        keys = [s['key'] for s in st['stages']]
        self.assertIn('risk_register', keys)
        stage = next(s for s in st['stages'] if s['key'] == 'risk_register')
        self.assertEqual(stage['title'], 'سجل المخاطر والمعالجة')


class RiskAdminTests(TestCase):
    def test_risk_models_registered_in_admin(self):
        from django.contrib import admin
        self.assertIn(RiskItem, admin.site._registry)
        self.assertIn(RemediationTask, admin.site._registry)


class RiskSafetyTests(TestCase):
    def setUp(self):
        self.c = _company()
        self.client.force_login(_journey_user(self.c))

    def _create_risk(self):
        self.client.post(reverse('risk:create'), {
            'title': 'X', 'description': '', 'category': 'other',
            'likelihood': 2, 'impact': 2, 'status': 'open', 'owner_name': ''})

    def test_risk_feature_does_not_create_companycontrol(self):
        from compliance.models import CompanyControl
        before = CompanyControl.objects.count()
        self._create_risk()
        self.assertEqual(CompanyControl.objects.count(), before)

    def test_risk_feature_does_not_change_subscription(self):
        from billing.models import CompanySubscription
        from billing.subscription_access import company_has_active_subscription
        self._create_risk()
        self.assertFalse(company_has_active_subscription(self.c))
        self.assertEqual(CompanySubscription.objects.filter(company=self.c).count(), 0)

    def test_risk_feature_does_not_change_report_exports(self):
        # Reports stay subscription-gated; an unsubscribed company still cannot export.
        c, fv, scope = _company_with_assessments()
        _risk(c, 5, 5)
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:export_evidence_matrix_csv'))
        self.assertNotEqual(resp.get('Content-Type'), 'text/csv')

    def test_risk_feature_does_not_import_otcc_dcc(self):
        from compliance.models import Control
        self._create_risk()
        self.assertFalse(Control.objects.filter(control_id__icontains='OTCC').exists())
        self.assertFalse(Control.objects.filter(control_id__icontains='DCC').exists())


class Phase5ABackwardCompatTests(TestCase):
    def setUp(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())

    def _register(self, cr='3030303030', email='bc5a@co.example'):
        return self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': email, 'phone': '',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': cr,
            'sector': 'technology', 'size': 'small', 'target_nca': 'on'})

    def test_company_registration_still_works(self):
        self.assertEqual(self._register().status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='3030303030').exists())

    def test_onboarding_still_works(self):
        self._register(cr='3131313131', email='bc5a2@co.example')
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_subscription_gated_reports_still_work(self):
        c, fv, scope = _company_with_assessments()
        self.client.force_login(_journey_user(c))
        self.assertContains(self.client.get(reverse('compliance:report_executive_summary')),
                            'تفعيل الاشتراك مطلوب')

    def test_auditor_assignment_still_works(self):
        from auditors.tests import _company_user
        from auditors.models import AuditorAssignment
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=c, auditor=p).count(), 1)

    def test_workflow_stepper_still_works(self):
        c = _company()
        self.client.force_login(_journey_user(c))
        self.assertContains(self.client.get(reverse('compliance:dashboard')), 'مسار عمل الشركة')

    def test_uat_seed_command_still_dry_run_safe(self):
        from io import StringIO
        from django.core.management import call_command
        before = (Company.objects.count(), User.objects.count())
        out = StringIO()
        call_command('seed_uat_demo_data', stdout=out)
        self.assertIn('DRY-RUN', out.getvalue())
        self.assertEqual((Company.objects.count(), User.objects.count()), before)

    def test_reports_still_work(self):
        from auditors.tests import _company_user
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        self.assertEqual(self.client.get(reverse('compliance:report_executive_summary')).status_code, 200)

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

    def test_staff_controlassessment_flow_still_works(self):
        from compliance.control_assessment import update_assessment_from_auditor_input
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        staff = _journey_user(c, email='staff5a@x.com', is_staff=True)
        update_assessment_from_auditor_input(a, {'status': 'compliant'}, staff)
        a.refresh_from_db()
        self.assertEqual(a.status, 'compliant')
