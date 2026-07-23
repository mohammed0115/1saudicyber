"""P0-01 — tenant-isolation / object-level authorization security tests.

Focus on the finding this phase fixed (auditor privilege must end when the assignment
ends) plus the evidence-pipeline defense-in-depth tripwire. Broader cross-company IDOR
coverage already lives in api/tests.py (EvidenceAnalyzeIsolationTests), risk/tests.py
(RiskAggregation + permission tests), monitoring/tests.py and compliance/tests_security_scope_guard.py.
"""
from django.test import TestCase
from django.urls import reverse

from auditors.models import AuditorAssignment
from auditors.services import get_auditor_profile
from compliance.models import Assessment, Evidence
from compliance.tests import _company_with_control, _assigned_auditor_user
from auditor_portal.tests import _company_control


class AuditorDeprovisioningTests(TestCase):
    """FINDING 1 — an auditor keeps `assigned_auditor` on the Assessment after the
    underlying assignment is cancelled/rejected; access must be revoked (404) anyway."""

    def _setup(self, email):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))   # wires the Assessment
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        return c, ctl, aud, a, cc

    def _assignment(self, aud, company):
        return AuditorAssignment.objects.get(auditor=get_auditor_profile(aud), company=company)

    # --- baseline: a live accepted assignment still works ---
    def test_accepted_auditor_can_open_assessment_and_control(self):
        c, ctl, aud, a, cc = self._setup('dep_ok@x.com')
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_assessment', args=[a.id])).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_control', args=[a.id, cc.id])).status_code, 200)

    # --- revocation on cancel ---
    def test_cancelled_assignment_revokes_assessment_read(self):
        c, ctl, aud, a, cc = self._setup('dep_cancel@x.com')
        asg = self._assignment(aud, c); asg.status = 'cancelled'; asg.save(update_fields=['status'])
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_assessment', args=[a.id])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_control', args=[a.id, cc.id])).status_code, 404)

    # --- revocation on reject blocks WRITES (verdict) ---
    def test_rejected_assignment_blocks_save_verdict_write(self):
        c, ctl, aud, a, cc = self._setup('dep_reject@x.com')
        asg = self._assignment(aud, c); asg.status = 'rejected'; asg.save(update_fields=['status'])
        from auditor_portal.models import AuditorControlVerdict
        resp = self.client.post(reverse('auditor_portal:save_verdict', args=[a.id, cc.id]),
                                {'status': 'compliant'})
        self.assertEqual(resp.status_code, 404)                # write refused
        self.assertEqual(AuditorControlVerdict.objects.count(), 0)   # nothing written

    def test_cancelled_assignment_blocks_rfi_create(self):
        c, ctl, aud, a, cc = self._setup('dep_rfi@x.com')
        asg = self._assignment(aud, c); asg.status = 'cancelled'; asg.save(update_fields=['status'])
        from auditor_portal.models import DocumentRequest
        resp = self.client.post(reverse('auditor_portal:request_document', args=[a.id, cc.id]),
                                {'description': 'x', 'title': 'y'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(DocumentRequest.objects.count(), 0)

    def test_cancelled_assignment_blocks_submit_report(self):
        c, ctl, aud, a, cc = self._setup('dep_report@x.com')
        asg = self._assignment(aud, c); asg.status = 'cancelled'; asg.save(update_fields=['status'])
        from auditor_portal.models import AuditReport
        resp = self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                                {'verdict': 'pass', 'executive_summary': 's'})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())

    def test_reassigned_to_a_second_company_does_not_grant_the_first(self):
        # Auditor loses company A (cancelled) — even while globally active — cannot touch A.
        c, ctl, aud, a, cc = self._setup('dep_multi@x.com')
        asg = self._assignment(aud, c); asg.status = 'cancelled'; asg.save(update_fields=['status'])
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_assessment', args=[a.id])).status_code, 404)


class EvidencePipelineDefenseTests(TestCase):
    """DD-1/DD-2 — the raw-id pipeline refuses to process an Evidence that does not belong
    to the company the caller asserts (defense-in-depth tripwire)."""

    def test_pipeline_refuses_cross_company_expected_id(self):
        from compliance.services import process_evidence_pipeline
        c, ctl = _company_with_control()
        cc = _company_control(c, ctl)
        ev = Evidence.objects.create(company_control=cc, uploaded_by=None,
                                     original_filename='x.pdf', file_type='pdf',
                                     file_size=8, status='uploaded')
        wrong_company_id = c.id + 9999
        res = process_evidence_pipeline(ev.id, expected_company_id=wrong_company_id)
        self.assertEqual(res.get('error'), 'evidence not found')  # 404-equivalent, no leak
        ev.refresh_from_db()
        self.assertEqual(ev.status, 'uploaded')                  # never mutated
