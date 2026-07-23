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

    def test_same_state_transition_is_rejected(self):
        # No silent no-op: same-state (incl. completed->completed re-issue) must raise.
        with self.assertRaises(InvalidAssessmentTransition):
            Assessment(status='auditor_review').transition_to('auditor_review', save=False)
        with self.assertRaises(InvalidAssessmentTransition):
            Assessment(status='completed').transition_to('completed', save=False)

    def test_stage_skipping_to_completed_is_rejected(self):
        # Nothing may skip auditor review to reach 'completed'.
        for dead in ('draft', 'in_progress', 'ai_complete'):
            self.assertFalse(Assessment(status=dead).can_transition_to('completed'))
            with self.assertRaises(InvalidAssessmentTransition):
                Assessment(status=dead).transition_to('completed', save=False)
            # legacy states may only advance forward to auditor_review
            self.assertTrue(Assessment(status=dead).can_transition_to('auditor_review'))


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


class CompletionPreconditionTests(TestCase):
    """Fail-closed completion gate (validate_ready_for_completion via submit_report)."""

    def _setup(self, email):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        return c, ctl, aud, a, cc

    def test_no_completion_from_wrong_state(self):
        from auditor_portal.lifecycle import validate_ready_for_completion, CompletionError
        c, ctl, aud, a, cc = self._setup('pre_state@x.com')
        a.status = 'draft'; a.save(update_fields=['status'])
        with self.assertRaises(CompletionError):
            validate_ready_for_completion(a, aud, 'pass')

    def test_no_completion_when_assignment_cancelled(self):
        from auditor_portal.models import AuditReport
        from auditors.models import AuditorAssignment
        from auditors.services import get_auditor_profile
        c, ctl, aud, a, cc = self._setup('pre_asg@x.com')
        AuditorAssignment.objects.filter(auditor=get_auditor_profile(aud), company=c).update(status='cancelled')
        # de-provisioned auditor cannot even reach submit_report (404 from the live-engagement guard)
        resp = self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())

    def test_no_completion_with_open_rfi(self):
        from auditor_portal.models import AuditReport
        c, ctl, aud, a, cc = self._setup('pre_rfi@x.com')
        DocumentRequest.objects.create(assessment=a, company_control=cc, auditor=aud,
                                       description='x', status='open')
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db()
        self.assertNotEqual(a.status, 'completed')
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())

    def test_pass_rejected_when_a_control_is_non_compliant(self):
        from auditor_portal.models import AuditReport
        c, ctl, aud, a, cc = self._setup('pre_incons@x.com')
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc, auditor=aud,
                                             status='non_compliant', rationale='r')
        # inconsistent 'pass' is refused
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db()
        self.assertNotEqual(a.status, 'completed')
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())
        # a consistent 'fail' finalizes
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'fail'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'completed')
        self.assertEqual(AuditReport.objects.get(assessment=a).verdict, 'fail')

    def test_missing_verdict_rejected(self):
        from auditor_portal.models import AuditReport
        c, ctl, aud, a, cc = self._setup('pre_missing@x.com')
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {})  # no verdict
        a.refresh_from_db()
        self.assertNotEqual(a.status, 'completed')
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())


class ReportImmutabilityTests(TestCase):
    def _issue(self, email, verdict='pass'):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': verdict})
        return a, AuditReport.objects.get(assessment=a)

    def test_issued_report_has_integrity_envelope(self):
        a, rep = self._issue('imm_env@x.com')
        self.assertTrue(rep.content_hash)
        self.assertTrue(rep.verify_integrity())
        self.assertEqual(rep.assessment_status_at_issue, 'completed')
        self.assertIsNotNone(rep.submitted_at)      # issued_at
        self.assertIsNotNone(rep.auditor_id)        # issued_by

    def test_save_on_issued_report_is_refused(self):
        from auditor_portal.models import ReportImmutableError
        a, rep = self._issue('imm_save@x.com')
        rep.verdict = 'fail'
        with self.assertRaises(ReportImmutableError):
            rep.save()

    def test_delete_on_issued_report_is_refused(self):
        from auditor_portal.models import ReportImmutableError
        a, rep = self._issue('imm_del@x.com')
        with self.assertRaises(ReportImmutableError):
            rep.delete()
        self.assertTrue(AuditReport.objects.filter(pk=rep.pk).exists())


class EvidenceSnapshotTests(TestCase):
    def test_report_captures_evidence_versions_and_new_uploads_do_not_change_it(self):
        from compliance.tests import _company_with_submission_file
        from compliance.models import EvidenceSubmission
        # A company with an evidence submission, plus an auditor assignment + assessment.
        c, item, sub = _company_with_submission_file(filename='e1.txt', content=b'v1', file_type='txt')
        aud = _assigned_auditor_user(c, email='snap_aud@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        rep = AuditReport.objects.get(assessment=a)
        snap_ids = {e['submission_id'] for e in rep.evidence_snapshot}
        self.assertIn(sub.id, snap_ids)
        self.assertTrue(any(e['filename'] == 'e1.txt' for e in rep.evidence_snapshot))
        before = list(rep.evidence_snapshot)
        # A NEW submission after completion must NOT alter the frozen snapshot.
        EvidenceSubmission.objects.create(company=c, checklist_item=item,
                                          original_filename='later.txt', file_type='txt', file_size=2)
        rep.refresh_from_db()
        self.assertEqual(rep.evidence_snapshot, before)
        self.assertTrue(rep.verify_integrity())


class RfiRespondAtomicityTests(TestCase):
    def test_response_and_status_are_atomic_rollback_on_failure(self):
        from auditor_portal.models import CompanyRFIResponse
        from unittest import mock
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='rfi_atom_aud@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        rfi = DocumentRequest.objects.create(assessment=a, company_control=cc, auditor=aud,
                                             description='x', status='open')
        cu = _journey_user(c, email='rfi_atom_cu@x.com')
        self.client.force_login(cu)
        # Force the status-save to blow up AFTER the response insert -> whole txn must roll back.
        with mock.patch('auditor_portal.models.DocumentRequest.save', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('auditor_portal:company_rfi_respond', args=[rfi.id]),
                                 {'response_text': 'hi'})
        self.assertEqual(CompanyRFIResponse.objects.filter(request=rfi).count(), 0)  # rolled back
        rfi.refresh_from_db()
        self.assertEqual(rfi.status, 'open')                                          # unchanged


class CertifiedInventoryTests(TestCase):
    def test_company_status_is_readonly_in_admin(self):
        from django.contrib import admin
        from core.models import Company
        ma = admin.site._registry[Company]
        self.assertIn('status', ma.readonly_fields)   # cannot hand-set 'certified' via admin

    def test_submit_report_does_not_expose_certified_transition(self):
        # Company.status has no code path to 'certified' (only classified/in_assessment are set).
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='inv_aud@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        c.refresh_from_db()
        self.assertNotEqual(c.status, 'certified')


class LockedUiTests(TestCase):
    def test_completed_assessment_hides_edit_forms_and_shows_locked_banner(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='ui_aud@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        # before close: the verdict edit form is present
        body = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertIn(reverse('auditor_portal:save_verdict', args=[a.id, cc.id]), body)
        # finalize, then the edit forms are hidden and a locked banner is shown
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        body2 = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertNotIn(reverse('auditor_portal:save_verdict', args=[a.id, cc.id]), body2)
        self.assertNotIn(reverse('auditor_portal:add_note', args=[a.id, cc.id]), body2)
        self.assertIn('نهائي ومُغلق', body2)


class SubmitIdempotencyTests(TestCase):
    def test_repeated_submit_is_idempotent_single_report(self):
        # SQLite test DB: proves request-level idempotency (OneToOne + terminal guard). True
        # row-lock concurrency must be verified on PostgreSQL in CI (see report Remaining Risks).
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='idem_aud@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        for _ in range(3):
            self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        self.assertEqual(AuditReport.objects.filter(assessment=a).count(), 1)
