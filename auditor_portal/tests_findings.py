"""G2 (findings + CAPA) and G1 (maturity scoring) — audit-core service + UI tests."""
from django.test import TestCase
from django.urls import reverse

from compliance.models import Assessment, CompanyControl, Framework, Domain, Control
from compliance.tests import _company_with_control, _assigned_auditor_user, _journey_user
from auditor_portal.models import AuditFinding, CorrectiveAction, AuditorControlVerdict
from auditor_portal import findings_service as fs


def _assessment(company, auditor):
    return Assessment.objects.create(company=company, assessment_type='formal_audit',
                                     assigned_auditor=auditor)


class FindingsServiceTests(TestCase):
    def _setup(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='find@x.com')
        a = _assessment(c, aud)
        cc = CompanyControl.objects.get_or_create(company=c, control=ctl)[0]
        return c, aud, a, cc

    def test_create_finding_defaults_open(self):
        c, aud, a, cc = self._setup()
        f = fs.create_finding(a, cc, aud, severity='major_nc',
                              title='لا يوجد تحقّق ثنائي', description='لا MFA على حسابات المشرفين.')
        self.assertEqual(f.status, 'open')
        self.assertTrue(f.is_open)
        self.assertEqual(f.severity_ar, 'عدم مطابقة رئيسي')

    def test_invalid_severity_and_empty_fields_rejected(self):
        c, aud, a, cc = self._setup()
        with self.assertRaises(ValueError):
            fs.create_finding(a, cc, aud, severity='bogus', title='x', description='y')
        with self.assertRaises(ValueError):
            fs.create_finding(a, cc, aud, severity='minor_nc', title='  ', description='y')

    def test_first_capa_moves_finding_to_remediation(self):
        c, aud, a, cc = self._setup()
        f = fs.create_finding(a, cc, aud, severity='minor_nc', title='t', description='d')
        fs.add_corrective_action(f, description='تفعيل MFA', owner='فريق تقنية', created_by=aud)
        f.refresh_from_db()
        self.assertEqual(f.status, 'in_remediation')
        self.assertEqual(CorrectiveAction.objects.filter(finding=f).count(), 1)

    def test_lifecycle_transitions_and_guards(self):
        c, aud, a, cc = self._setup()
        f = fs.create_finding(a, cc, aud, severity='major_nc', title='t', description='d')
        fs.add_corrective_action(f, description='x', created_by=aud)      # open -> in_remediation
        fs.transition_finding(f, 'reverify')
        fs.transition_finding(f, 'closed')
        self.assertEqual(f.status, 'closed')
        with self.assertRaises(ValueError):
            fs.transition_finding(f, 'in_remediation')                    # closed -> remediation invalid
        fs.transition_finding(f, 'reopened')                              # closed -> reopened valid
        self.assertEqual(f.status, 'reopened')

    def test_verify_corrective_action(self):
        c, aud, a, cc = self._setup()
        f = fs.create_finding(a, cc, aud, severity='minor_nc', title='t', description='d')
        action = fs.add_corrective_action(f, description='remediate', created_by=aud)
        fs.verify_corrective_action(action, note='أُعيد الاختبار — سليم')
        action.refresh_from_db()
        self.assertEqual(action.status, 'verified')
        self.assertEqual(action.verification_note, 'أُعيد الاختبار — سليم')


class MaturityScoreTests(TestCase):
    def _controls(self, company, n):
        fw = Framework.objects.get_or_create(code='NCA', defaults={'name': 'NCA'})[0]
        dom = Domain.objects.get_or_create(framework=fw, name='حوكمة', defaults={'code': 'GOV'})[0]
        out = []
        for i in range(n):
            ctl = Control.objects.create(framework=fw, domain=dom, control_id='M-%d' % i,
                                         title='C%d' % i, description='d')
            out.append(CompanyControl.objects.create(company=company, control=ctl))
        return out

    def test_domain_maturity_percentage_excludes_na_and_unset(self):
        c, _ = _company_with_control()
        aud = _assigned_auditor_user(c, email='mat@x.com')
        a = _assessment(c, aud)
        ccs = self._controls(c, 4)
        levels = ['implemented', 'partially_implemented', 'not_applicable', '']
        for cc, lvl in zip(ccs, levels):
            AuditorControlVerdict.objects.create(assessment=a, company_control=cc,
                                                 status='compliant', implementation_level=lvl)
        res = fs.assessment_maturity(a)
        # implemented(1.0) + partially(0.5) over 2 scored = 75%; NA and unset excluded.
        self.assertEqual(res['assessed_count'], 2)
        self.assertEqual(res['overall_pct'], 75)
        self.assertEqual(res['domains'][0]['name'], 'حوكمة')
        self.assertEqual(res['domains'][0]['pct'], 75)

    def test_no_levels_yields_zero(self):
        c, _ = _company_with_control()
        aud = _assigned_auditor_user(c, email='mat0@x.com')
        a = _assessment(c, aud)
        self.assertEqual(fs.assessment_maturity(a), {'overall_pct': 0, 'assessed_count': 0, 'domains': []})


class FindingsUITests(TestCase):
    def _setup(self, email='fui@x.com'):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = CompanyControl.objects.get_or_create(company=c, control=ctl)[0]
        return c, ctl, aud, a, cc

    def _url(self, name, a, cc):
        return reverse(name, args=[a.id, cc.id])

    def test_review_control_renders_findings_section(self):
        c, ctl, aud, a, cc = self._setup()
        body = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertIn('الملاحظات (عدم المطابقة)', body)
        self.assertIn('مستوى التطبيق', body)   # G1 maturity select present

    def test_add_finding_creates(self):
        c, ctl, aud, a, cc = self._setup(email='fui_add@x.com')
        resp = self.client.post(self._url('auditor_portal:add_finding', a, cc),
                                {'severity': 'major_nc', 'title': 'ثغرة', 'description': 'وصف الثغرة.'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AuditFinding.objects.filter(assessment=a, company_control=cc).count(), 1)

    def test_add_finding_get_is_405(self):
        c, ctl, aud, a, cc = self._setup(email='fui_get@x.com')
        self.assertEqual(self.client.get(self._url('auditor_portal:add_finding', a, cc)).status_code, 405)

    def test_add_finding_cross_tenant_blocked(self):
        c, ctl, aud, a, cc = self._setup(email='fui_a@x.com')
        aud2 = _assigned_auditor_user(c, email='fui_b@x.com')  # a different auditor, NOT a.assigned_auditor
        self.client.force_login(aud2)                       # not assigned to assessment `a`
        resp = self.client.post(self._url('auditor_portal:add_finding', a, cc),
                                {'severity': 'minor_nc', 'title': 't', 'description': 'd'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(AuditFinding.objects.filter(assessment=a).count(), 0)

    def test_save_verdict_persists_implementation_level(self):
        c, ctl, aud, a, cc = self._setup(email='fui_lvl@x.com')
        self.client.post(self._url('auditor_portal:save_verdict', a, cc),
                         {'status': 'partially_compliant', 'rationale': 'جزئي',
                          'recommendation': 'أكمل', 'implementation_level': 'partially_implemented'})
        v = AuditorControlVerdict.objects.get(assessment=a, company_control=cc)
        self.assertEqual(v.implementation_level, 'partially_implemented')


class CapaAndCompanyUITests(TestCase):
    def _finding(self, email='capa@x.com'):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = CompanyControl.objects.get_or_create(company=c, control=ctl)[0]
        f = fs.create_finding(a, cc, aud, severity='major_nc', title='t', description='d')
        return c, aud, a, cc, f

    def test_auditor_adds_capa_then_verifies(self):
        c, aud, a, cc, f = self._finding()
        r1 = self.client.post(reverse('auditor_portal:add_corrective_action', args=[f.id]),
                              {'description': 'تفعيل MFA', 'owner': 'IT', 'due_date': '2026-09-01'})
        self.assertEqual(r1.status_code, 302)
        action = CorrectiveAction.objects.get(finding=f)
        f.refresh_from_db()
        self.assertEqual(f.status, 'in_remediation')       # first CAPA moved it
        self.assertEqual(action.due_date.isoformat(), '2026-09-01')
        self.client.post(reverse('auditor_portal:verify_corrective_action', args=[action.id]),
                         {'note': 'أُعيد الاختبار'})
        action.refresh_from_db()
        self.assertEqual(action.status, 'verified')

    def test_finding_status_transition_view(self):
        c, aud, a, cc, f = self._finding(email='capa_tr@x.com')
        self.client.post(reverse('auditor_portal:update_finding_status', args=[f.id]),
                         {'status': 'in_remediation'})
        f.refresh_from_db()
        self.assertEqual(f.status, 'in_remediation')

    def test_capa_cross_tenant_blocked(self):
        c, aud, a, cc, f = self._finding(email='capa_x@x.com')
        other = _assigned_auditor_user(c, email='capa_x2@x.com')   # not this assessment's auditor
        self.client.force_login(other)
        r = self.client.post(reverse('auditor_portal:add_corrective_action', args=[f.id]),
                             {'description': 'x'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(CorrectiveAction.objects.filter(finding=f).count(), 0)

    def test_company_views_and_adds_capa(self):
        c, aud, a, cc, f = self._finding(email='capa_co@x.com')
        self.client.force_login(_journey_user(c, email='co_user@x.com'))
        body = self.client.get(reverse('auditor_portal:company_findings')).content.decode()
        self.assertIn('ملاحظات التدقيق', body)
        self.assertIn('t', body)
        self.client.post(reverse('auditor_portal:company_add_corrective_action', args=[f.id]),
                         {'description': 'سننفّذ الضابط', 'owner': 'مدير تقنية'})
        self.assertEqual(CorrectiveAction.objects.filter(finding=f).count(), 1)

    def test_company_cannot_touch_other_company_finding(self):
        from core.models import Company
        c, aud, a, cc, f = self._finding(email='capa_iso@x.com')
        c2 = Company.objects.create(name='Other', cr_number='7788990011', sector='technology',
                                    size='small', contact_email='oc@x.com')
        self.client.force_login(_journey_user(c2, email='other_co@x.com'))
        r = self.client.post(reverse('auditor_portal:company_add_corrective_action', args=[f.id]),
                             {'description': 'x'})
        self.assertEqual(r.status_code, 404)

    def test_maturity_scorecard_renders_in_review_assessment(self):
        c, aud, a, cc, f = self._finding(email='mat_ui@x.com')
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc,
                                             status='compliant', implementation_level='implemented')
        self.client.force_login(aud)
        body = self.client.get(reverse('auditor_portal:review_assessment', args=[a.id])).content.decode()
        self.assertIn('بطاقة النضج', body)

    def test_findings_rollup_in_review_assessment(self):
        c, aud, a, cc, f = self._finding(email='roll@x.com')
        self.client.force_login(aud)
        body = self.client.get(reverse('auditor_portal:review_assessment', args=[a.id])).content.decode()
        self.assertIn('الملاحظات (عدم المطابقة)', body)
        self.assertIn(f.title, body)

    def test_company_advances_capa_progress(self):
        from auditor_portal.models import CorrectiveAction
        c, aud, a, cc, f = self._finding(email='capa_adv@x.com')
        action = fs.add_corrective_action(f, description='خطة', created_by=aud)   # planned
        self.client.force_login(_journey_user(c, email='capa_adv_co@x.com'))
        self.client.post(reverse('auditor_portal:company_update_capa', args=[action.id]),
                         {'status': 'in_progress'})
        action.refresh_from_db()
        self.assertEqual(action.status, 'in_progress')
        self.client.post(reverse('auditor_portal:company_update_capa', args=[action.id]),
                         {'status': 'done'})
        action.refresh_from_db()
        self.assertEqual(action.status, 'done')

    def test_advance_capa_invalid_transition_rejected(self):
        c, aud, a, cc, f = self._finding(email='capa_bad@x.com')
        action = fs.add_corrective_action(f, description='خطة', created_by=aud)
        fs.verify_corrective_action(action)   # -> verified (terminal)
        with self.assertRaises(ValueError):
            fs.advance_corrective_action(action, 'in_progress')

    def test_submit_report_serializes_findings_and_maturity(self):
        from auditor_portal.models import AuditReport
        c, aud, a, cc, f = self._finding(email='rep@x.com')
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc,
                                             status='compliant', implementation_level='implemented')
        self.client.force_login(aud)
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                         {'verdict': 'conditional_pass', 'executive_summary': 'ملخص'})
        rep = AuditReport.objects.get(assessment=a)
        self.assertEqual(len(rep.findings), 1)
        self.assertEqual(rep.findings[0]['title'], f.title)
        self.assertEqual(rep.recommendations[0]['overall_pct'], 100)   # maturity embedded

    def test_admin_company_detail_shows_findings_panel(self):
        from core.models import User
        c, aud, a, cc, f = self._finding(email='adm_f@x.com')
        staff = User.objects.create_user(email='adm_panel@x.com', username='adm_panel@x.com',
                                         password='longenough12', role='admin', is_staff=True)
        self.client.force_login(staff)
        body = self.client.get(reverse('platform_admin:company_detail', args=[c.id])).content.decode()
        self.assertIn('ملاحظات التدقيق والنضج', body)
        self.assertIn(f.title, body)
