"""Tests for the auditor-verdict -> EvidenceSubmission.status coupling.

A recorded AuditorFinalVerdict now advances the evidence FILE lifecycle so it no longer
reads pending_review after human review:
  any final_* verdict            -> submission.status = accepted
  needs_more_evidence            -> submission.status = needs_reupload (+ rejection_reason)
A non-compliant verdict is NOT a rejected file. No models/urls/views/migrations changed.
"""
from django.test import TestCase
from django.urls import reverse

from compliance.tests import (_company_with_submission, _staff_user, _journey_user,
                              _assigned_auditor_user)
from compliance.auditor_verdict import record_auditor_final_verdict, VerdictError


class VerdictSubmissionStatusTests(TestCase):
    def _nca(self):
        return _company_with_submission(fv_code='NCA-ECC-2-2024')

    def _aramco(self):
        return _company_with_submission(fv_code='ARAMCO-SACS-002')

    def test_final_c_marks_submission_accepted(self):
        c, item, sub = self._nca()
        record_auditor_final_verdict(sub, _staff_user(), status='final_c', rationale='تمت المراجعة.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')

    def test_final_compliance_marks_submission_accepted(self):
        c, item, sub = self._aramco()
        record_auditor_final_verdict(sub, _staff_user('a1@x.com'), status='final_compliance',
                                     rationale='ok')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')

    def test_final_nc_is_accepted_not_rejected(self):
        # Non-compliant CONTROL != rejected evidence FILE.
        c, item, sub = self._nca()
        record_auditor_final_verdict(sub, _staff_user('a2@x.com'), status='final_nc',
                                     rationale='الضابط غير ممتثل، لكن الدليل صحيح.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')
        self.assertNotEqual(sub.status, 'rejected')

    def test_final_noncompliance_is_accepted_not_rejected(self):
        c, item, sub = self._aramco()
        record_auditor_final_verdict(sub, _staff_user('a3@x.com'), status='final_noncompliance',
                                     rationale='غير ممتثل.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')

    def test_needs_more_evidence_marks_needs_reupload_with_reason(self):
        c, item, sub = self._nca()
        record_auditor_final_verdict(sub, _staff_user('a4@x.com'), status='needs_more_evidence',
                                     rationale='الدليل غير كافٍ، يرجى رفع سياسة موقّعة.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'needs_reupload')
        self.assertIn('غير كافٍ', sub.rejection_reason)

    def test_reverdict_from_needs_more_evidence_to_final_c_clears_reason(self):
        c, item, sub = self._nca()
        staff = _staff_user('a5@x.com')
        record_auditor_final_verdict(sub, staff, status='needs_more_evidence', rationale='ناقص.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'needs_reupload')
        self.assertTrue(sub.rejection_reason)
        # Auditor changes their mind after a re-upload.
        record_auditor_final_verdict(sub, staff, status='final_c', rationale='أصبح مكتملًا.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')
        self.assertEqual(sub.rejection_reason, '')          # stale re-upload reason cleared

    def test_assigned_auditor_verdict_updates_status(self):
        c, item, sub = self._nca()
        u = _assigned_auditor_user(c, email='aud_vs@x.com')
        record_auditor_final_verdict(sub, u, status='final_pc', rationale='جزئي لكن مقبول كدليل.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'accepted')

    def test_unauthorized_user_cannot_change_status(self):
        c, item, sub = self._nca()
        before = sub.status
        with self.assertRaises(VerdictError):
            record_auditor_final_verdict(sub, _journey_user(c, email='co_vs@x.com'),
                                         status='final_c', rationale='محاولة غير مصرّح بها.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, before)                # unchanged (still pending_review)
        self.assertEqual(sub.status, 'pending_review')

    def test_evidence_list_shows_file_and_compliance_badges_after_verdict(self):
        # UX: the FILE badge ("Evidence accepted") and the COMPLIANCE badge ("Compliant")
        # are two SEPARATE dimensions — the file being accepted is NOT a compliance pass.
        c, item, sub = self._nca()
        record_auditor_final_verdict(sub, _staff_user('a6@x.com'), status='final_c', rationale='تم.')
        self.client.force_login(_journey_user(c, email='co_list@x.com'))
        body = self.client.get(
            reverse('compliance:evidence_submission_list', args=[item.id])).content.decode()
        self.assertIn('Evidence accepted', body)          # file lifecycle badge
        self.assertIn('Compliant', body)                  # separate compliance-verdict badge
        self.assertIn('مقبول', body)
        self.assertNotIn('Pending auditor review', body)
        # Regression: the evidence_status component must not leak its developer comment
        # (a multi-line {# #} does NOT comment in Django and would render into the page).
        self.assertNotIn('cognitive conflation', body)
        self.assertNotIn('INDEPENDENT dimensions', body)

    def test_noncompliant_verdict_still_shows_evidence_accepted(self):
        # A non-compliant CONTROL must not read as a rejected FILE, and must not read as
        # compliant either — both badges must be present and distinct.
        c, item, sub = self._nca()
        record_auditor_final_verdict(sub, _staff_user('a7@x.com'), status='final_nc', rationale='غير متوافق.')
        self.client.force_login(_journey_user(c, email='co_nc@x.com'))
        body = self.client.get(
            reverse('compliance:evidence_submission_list', args=[item.id])).content.decode()
        self.assertIn('Evidence accepted', body)          # file accepted
        self.assertIn('Non-compliant', body)              # but control is NOT compliant
        self.assertNotIn('Rejected', body)


class VerdictAuditorGuardTests(TestCase):
    """Regression: is_active_auditor() must be CALLED — a pending/suspended auditor with an
    accepted assignment must NOT be able to record a verdict or change submission status."""

    def test_pending_auditor_cannot_record_verdict(self):
        from auditors.models import AuditorProfile, AuditorAssignment
        from core.models import User
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        u = User.objects.create_user(email='pendaud@x.com', password='longenough12', role='auditor')
        p = AuditorProfile.objects.create(user=u, full_name='P', status='pending_review')
        AuditorAssignment.objects.create(company=c, auditor=p, status='accepted')
        with self.assertRaises(VerdictError):
            record_auditor_final_verdict(sub, u, status='final_c', rationale='محاولة معلّق.')
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'pending_review')


class VerdictIndependenceTests(TestCase):
    """P1-5: nobody affiliated with the audited company may sign its verdict."""

    def test_company_affiliated_staff_cannot_sign(self):
        from compliance.auditor_verdict import can_submit_final_verdict
        from core.models import User
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        insider = User.objects.create_user(email='insider@x.com', password='longenough12',
                                           is_staff=True, company=c)  # staff BUT of this company
        self.assertFalse(can_submit_final_verdict(insider, sub))
        with self.assertRaises(VerdictError):
            record_auditor_final_verdict(sub, insider, status='final_c', rationale='تعارض مصالح.')

    def test_independent_staff_can_sign(self):
        from compliance.auditor_verdict import can_submit_final_verdict
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        self.assertTrue(can_submit_final_verdict(_staff_user('indep@x.com'), sub))  # no company link
