"""
Regression test for PATCH_NOTES fix #4 (Prototype Phase 10B):
the realtime_monitoring view referenced templates/monitoring/realtime.html,
which previously did not exist -> TemplateDoesNotExist crash.
"""
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company


class RealtimeTemplateTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Co', cr_number='1313131313', sector='technology', size='small',
            contact_email='c@x.com', target_nca=True)
        self.user = User.objects.create_user(
            email='rt@x.com', password='longenough12', company=self.company, role='company_admin')
        self.client.force_login(self.user)

    def test_realtime_page_renders(self):
        resp = self.client.get(reverse('monitoring:realtime'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'monitoring/realtime.html')


# ============================================================
# Phase 5B — Continuous Monitoring Foundation tests
# ============================================================
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from monitoring.models import MonitoringCheck, MonitoringRun, MonitoringFinding
from monitoring import continuous

from compliance.tests import _company_with_assessments, _journey_user, _company_with_submission
from auditors.tests import _auditor, _assignment


def _mcompany(name='MonCo', cr=None):
    n = Company.objects.count() + 1
    return Company.objects.create(name=name, cr_number=cr or f'{6000000000 + n}',
                                  sector='technology', size='small', contact_email=f'm{n}@x.com')


def _check(company, check_type='manual_review', frequency='monthly', **kw):
    return MonitoringCheck.objects.create(
        company=company, title=kw.pop('title', 'Check'), check_type=check_type,
        frequency=frequency, **kw)


class MonitoringModelScheduleTests(TestCase):
    def test_model_creation(self):
        c = _mcompany()
        chk = _check(c)
        self.assertEqual(chk.last_result, 'not_run')
        self.assertEqual(chk.status, 'active')

    def test_next_run_calculation(self):
        now = timezone.now()
        self.assertEqual(continuous.calculate_next_run_at('daily', now), now + timedelta(days=1))
        self.assertEqual(continuous.calculate_next_run_at('weekly', now), now + timedelta(days=7))
        self.assertEqual(continuous.calculate_next_run_at('quarterly', now), now + timedelta(days=90))
        self.assertEqual(continuous.calculate_next_run_at('annual', now), now + timedelta(days=365))


class MonitoringCommandTests(TestCase):
    def _run(self, *args):
        out = StringIO()
        call_command('run_monitoring_checks', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_dry_run_command_writes_nothing(self):
        c = _mcompany()
        _check(c, 'manual_review')  # due (next_run_at null)
        before = (MonitoringRun.objects.count(), MonitoringFinding.objects.count())
        out = self._run()  # default dry-run
        self.assertIn('DRY-RUN', out)
        self.assertEqual((MonitoringRun.objects.count(), MonitoringFinding.objects.count()), before)

    def test_apply_command_creates_runs_and_findings(self):
        c = _mcompany()
        _check(c, 'manual_review')  # manual_review -> needs_review -> a finding
        self._run('--apply')
        self.assertEqual(MonitoringRun.objects.filter(company=c).count(), 1)
        self.assertEqual(MonitoringFinding.objects.filter(company=c).count(), 1)
        chk = MonitoringCheck.objects.get(company=c)
        self.assertEqual(chk.last_result, 'needs_review')
        self.assertIsNotNone(chk.last_run_at)
        self.assertIsNotNone(chk.next_run_at)

    def test_apply_reschedules_so_not_due_again(self):
        c = _mcompany()
        _check(c, 'manual_review')
        self._run('--apply')
        # Second apply: not due anymore -> no new run.
        self._run('--apply')
        self.assertEqual(MonitoringRun.objects.filter(company=c).count(), 1)


class MonitoringSafetyTests(TestCase):
    def test_risk_migration_unaffected(self):
        # The risk tables still work alongside the new monitoring tables.
        from risk.models import RiskItem
        c = _mcompany()
        RiskItem.objects.create(company=c, title='r', likelihood=2, impact=2)
        self.assertEqual(RiskItem.objects.filter(company=c).count(), 1)

    def test_monitoring_does_not_mutate_controlassessment(self):
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        chk = _check(c, 'control_status_review', control_assessment=a)
        before = {x.id: x.status for x in ControlAssessment.objects.filter(company=c)}
        continuous.run_monitoring_check(chk, apply=True)
        after = {x.id: x.status for x in ControlAssessment.objects.filter(company=c)}
        self.assertEqual(before, after)

    def test_evidence_freshness_and_remediation_checks_run(self):
        # Smoke: these evaluate without external calls and persist a run.
        from compliance.evidence_analysis import analyze_evidence_submission  # noqa
        c, item, sub = _company_with_submission()
        chk = _check(c, 'evidence_freshness', frequency='daily')
        res = continuous.run_monitoring_check(chk, apply=True)
        self.assertIn(res['status'], ('pass', 'needs_review', 'fail'))
        self.assertTrue(MonitoringRun.objects.filter(monitoring_check=chk).exists())


class MonitoringPermissionTests(TestCase):
    def test_anonymous_redirect(self):
        for n in ['monitoring:overview', 'monitoring:checks', 'monitoring:findings']:
            resp = self.client.get(reverse(n))
            self.assertEqual(resp.status_code, 302, n)
            self.assertIn('/login', resp.url, n)

    def test_company_user_cannot_see_other_company_monitoring(self):
        a = _mcompany('A'); b = _mcompany('B', cr='6999999999')
        ca = _check(a, title='ACheck'); cb = _check(b, title='BCheck')
        self.client.force_login(_journey_user(a))
        resp = self.client.get(reverse('monitoring:checks'))
        self.assertContains(resp, 'ACheck')
        self.assertNotContains(resp, 'BCheck')

    def test_assigned_auditor_read_only_access(self):
        c, fv, scope = _company_with_assessments()
        _check(c, title='SeenByAuditor')
        u, p = _auditor(status='active')
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(reverse('monitoring:auditor_view', args=[a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'للقراءة فقط')

    def test_unassigned_auditor_cannot_view_monitoring(self):
        c, fv, scope = _company_with_assessments()
        u1, p1 = _auditor(status='active')
        u2, p2 = _auditor(status='active')
        a = _assignment(c, p2, status='accepted')
        self.client.force_login(u1)
        self.assertEqual(self.client.get(reverse('monitoring:auditor_view', args=[a.id])).status_code, 302)

    def test_pending_auditor_cannot_view_monitoring(self):
        c, fv, scope = _company_with_assessments()
        u, p = _auditor(status='pending_review')
        a = _assignment(c, p, status='accepted')
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('monitoring:auditor_view', args=[a.id])).status_code, 302)


class MonitoringDashboardTests(TestCase):
    def test_dashboard_counters_render(self):
        c = _mcompany()
        _check(c, 'risk_review')
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'المراقبة المستمرة')
        self.assertContains(resp, reverse('monitoring:overview'))

    def test_overview_page_arabic_rtl(self):
        c = _mcompany()
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('monitoring:overview'))
        self.assertContains(resp, 'dir="rtl"')
        self.assertContains(resp, 'المراقبة المستمرة')

    def test_summary_counts_are_read_only(self):
        c = _mcompany()
        _check(c, 'manual_review')
        before = (MonitoringRun.objects.count(), MonitoringFinding.objects.count())
        continuous.summarize_company_monitoring(c)
        self.assertEqual((MonitoringRun.objects.count(), MonitoringFinding.objects.count()), before)


class MonitoringAdminTests(TestCase):
    def test_models_registered_in_admin(self):
        from django.contrib import admin
        self.assertIn(MonitoringCheck, admin.site._registry)
        self.assertIn(MonitoringRun, admin.site._registry)
        self.assertIn(MonitoringFinding, admin.site._registry)
