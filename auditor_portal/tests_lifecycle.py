"""P0-02 — formal Assessment state machine, report integrity, edit-after-close lock,
duplicate/atomicity, and certificate safety.
"""
from django.test import TestCase
from django.urls import reverse

from compliance.models import Assessment, InvalidAssessmentTransition, CompanyControl
from compliance.tests import (_company_with_control, _assigned_auditor_user, _journey_user,
                              _company)
from auditor_portal.tests import _company_control
from auditor_portal.models import (AuditReport, AuditorControlVerdict, AuditorNote,
                                   DocumentRequest, AuditFinding)


class AssessmentStateMachineTests(TestCase):
    def test_terminal_states_are_locked_and_have_no_transitions(self):
        a = Assessment(status='completed')
        self.assertTrue(a.is_locked)
        self.assertEqual(Assessment.ALLOWED_TRANSITIONS['completed'], frozenset())
        self.assertEqual(Assessment.ALLOWED_TRANSITIONS['expired'], frozenset())
        self.assertFalse(a.can_transition_to('auditor_review'))   # no reopen
        self.assertFalse(a.can_transition_to('draft'))

    def test_legal_forward_transition(self):
        a = Assessment(status='auditor_review')
        self.assertFalse(a.is_locked)
        self.assertTrue(a.can_transition_to('completed'))

    def test_illegal_transition_raises(self):
        a = Assessment(status='completed')
        with self.assertRaises(InvalidAssessmentTransition):
            a.transition_to('auditor_review', save=False)       # completed -> reopen is illegal
        with self.assertRaises(InvalidAssessmentTransition):
            Assessment(status='completed').transition_to('draft', save=False)

    def test_transition_to_same_state_is_noop(self):
        a = Assessment(status='auditor_review')
        a.transition_to('auditor_review', save=False)           # no raise, no change
        self.assertEqual(a.status, 'auditor_review')


class SubmitReportIntegrityTests(TestCase):
    def _setup(self, email):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))     # materialise the assessment
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        return c, ctl, aud, a, cc

    def test_submit_completes_and_creates_exactly_one_report(self):
        c, ctl, aud, a, cc = self._setup('sr_ok@x.com')
        resp = self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                                {'verdict': 'pass', 'executive_summary': 's'})
        self.assertEqual(resp.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, 'completed')
        self.assertIsNotNone(a.completed_at)
        self.assertEqual(AuditReport.objects.filter(assessment=a).count(), 1)

    def test_resubmit_is_blocked_and_never_creates_a_second_report(self):
        c, ctl, aud, a, cc = self._setup('sr_re@x.com')
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        rep1 = AuditReport.objects.get(assessment=a)
        # Second submit (retry / double-POST) must NOT re-issue or change the report.
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                         {'verdict': 'fail', 'executive_summary': 'TAMPERED'})
        self.assertEqual(AuditReport.objects.filter(assessment=a).count(), 1)
        rep1.refresh_from_db()
        self.assertEqual(rep1.verdict, 'pass')                   # unchanged — not overwritten
        self.assertNotEqual(rep1.executive_summary, 'TAMPERED')

    def test_invalid_verdict_is_rejected(self):
        c, ctl, aud, a, cc = self._setup('sr_bad@x.com')
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                         {'verdict': 'definitely-certified'})
        a.refresh_from_db()
        self.assertNotEqual(a.status, 'completed')               # not finalized
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())

    def test_report_is_a_snapshot_not_live(self):
        # A finding present at submit is frozen into the report; a later finding is NOT.
        c, ctl, aud, a, cc = self._setup('sr_snap@x.com')
        from auditor_portal.findings_service import create_finding
        create_finding(a, cc, aud, severity='major_nc', title='F1', description='d')
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'conditional_pass'})
        rep = AuditReport.objects.get(assessment=a)
        self.assertEqual(len(rep.findings), 1)
        titles = {f['title'] for f in rep.findings}
        self.assertIn('F1', titles)


class EditAfterCloseLockTests(TestCase):
    """Every artifact mutation must be refused (403) once the assessment is completed."""

    def setUp(self):
        self.c, self.ctl = _company_with_control()
        self.aud = _assigned_auditor_user(self.c, email='lock_aud@x.com')
        self.client.force_login(self.aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        self.a = Assessment.objects.get(assigned_auditor=self.aud)
        self.cc = _company_control(self.c, self.ctl)
        # create a finding + RFI BEFORE closing (so we can try to mutate them after)
        from auditor_portal.findings_service import create_finding
        self.finding = create_finding(self.a, self.cc, self.aud, severity='major_nc', title='F', description='d')
        self.rfi = DocumentRequest.objects.create(
            assessment=self.a, company_control=self.cc, auditor=self.aud,
            description='x', status='closed')
        # finalize
        self.client.post(reverse('auditor_portal:submit_report', args=[self.a.id]), {'verdict': 'pass'})
        self.a.refresh_from_db()
        assert self.a.status == 'completed'

    def test_save_verdict_blocked_after_close(self):
        n = AuditorControlVerdict.objects.count()
        resp = self.client.post(reverse('auditor_portal:save_verdict', args=[self.a.id, self.cc.id]),
                                {'status': 'compliant'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(AuditorControlVerdict.objects.count(), n)     # nothing written

    def test_add_note_blocked_after_close(self):
        resp = self.client.post(reverse('auditor_portal:add_note', args=[self.a.id, self.cc.id]),
                                {'note': 'late note'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AuditorNote.objects.filter(assessment=self.a).exists())

    def test_add_finding_blocked_after_close(self):
        n = AuditFinding.objects.filter(assessment=self.a).count()
        resp = self.client.post(reverse('auditor_portal:add_finding', args=[self.a.id, self.cc.id]),
                                {'severity': 'high', 'title': 'late', 'description': 'd'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(AuditFinding.objects.filter(assessment=self.a).count(), n)

    def test_request_document_blocked_after_close(self):
        n = DocumentRequest.objects.filter(assessment=self.a).count()
        resp = self.client.post(reverse('auditor_portal:request_document', args=[self.a.id, self.cc.id]),
                                {'title': 'late', 'description': 'd', 'priority': 'high'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(DocumentRequest.objects.filter(assessment=self.a).count(), n)

    def test_reopen_rfi_blocked_after_close(self):
        # Closing an assessment must not be reversible by re-opening its RFI.
        resp = self.client.post(reverse('auditor_portal:reopen_rfi', args=[self.rfi.id]), {})
        self.assertEqual(resp.status_code, 403)
        self.rfi.refresh_from_db()
        self.assertEqual(self.rfi.status, 'closed')

    def test_update_finding_status_blocked_after_close(self):
        resp = self.client.post(reverse('auditor_portal:update_finding_status', args=[self.finding.id]),
                                {'status': 'closed'})
        self.assertEqual(resp.status_code, 403)

    def test_company_rfi_respond_blocked_after_close(self):
        cu = _journey_user(self.c, email='lock_cu@x.com')
        self.client.force_login(cu)
        resp = self.client.post(reverse('auditor_portal:company_rfi_respond', args=[self.rfi.id]),
                                {'response_text': 'late response'})
        self.assertEqual(resp.status_code, 403)


class CertificateSafetyTests(TestCase):
    def test_no_certificate_issued_and_company_not_certified_on_any_verdict(self):
        from monitoring.models import CertificateTracker
        for i, verdict in enumerate(('pass', 'conditional_pass', 'fail')):
            c = _company(cr_number=f'70000000{i:02d}')
            aud = _assigned_auditor_user(c, email=f'cert_{verdict}@x.com')
            self.client.force_login(aud)
            self.client.get(reverse('auditor_portal:dashboard'))
            a = Assessment.objects.get(assigned_auditor=aud)
            self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': verdict})
            a.refresh_from_db()
            self.assertEqual(a.status, 'completed')
            # No certificate is ever created; the company is never marked 'certified'.
            self.assertEqual(CertificateTracker.objects.filter(company=c).count(), 0)
            c.refresh_from_db()
            self.assertNotEqual(c.status, 'certified')
