"""URGENT hotfix regression tests — evidence upload 500 + detail 404 / empty checklist.

Covers the pilot blocker where a company with no generated evidence checklist hit a
500 on upload and a broken "View", plus tenant-isolation on evidence detail. Reuses the
proven compliance fixtures. No payment/Moyasar changes.
"""
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from compliance.tests import (_company_with_checklist, _company_with_submission,
                              _company, _journey_user, _SUF)
from compliance.models import EvidenceChecklistItem, EvidenceSubmission


class EvidenceEmptyChecklistTests(TestCase):
    def test_company_with_no_checklist_sees_clear_message_no_500(self):
        c = _company()
        self.client.force_login(_journey_user(c, email='noeic@x.com'))
        resp = self.client.get(reverse('compliance:evidence_checklist'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EvidenceChecklistItem.objects.filter(company=c).count(), 0)
        self.assertContains(resp, 'Complete Smart Classification first')

    def test_upload_against_nonexistent_item_is_safe_not_500(self):
        c = _company()
        self.client.force_login(_journey_user(c, email='noeic2@x.com'))
        resp = self.client.post(reverse('compliance:evidence_upload_v2', args=[999999]),
                                {'uploaded_file': _SUF('p.pdf', b'%PDF-1.4 ok')})
        self.assertEqual(resp.status_code, 302)  # redirected safely, never 500
        self.assertEqual(EvidenceSubmission.objects.filter(company=c).count(), 0)


class EvidenceUploadHotfixTests(TestCase):
    def setUp(self):
        self.c, self.fv, self.scope = _company_with_checklist()
        self.item = EvidenceChecklistItem.objects.filter(company=self.c).first()
        self.user = _journey_user(self.c, email='euhf@x.com')
        self.client.force_login(self.user)

    def _upload(self):
        return self.client.post(
            reverse('compliance:evidence_upload_v2', args=[self.item.id]),
            {'uploaded_file': _SUF('policy.pdf', b'%PDF-1.4 evidence'), 'notes': 'n'})

    def test_upload_creates_submission_with_correct_company_and_no_500(self):
        resp = self._upload()
        self.assertEqual(resp.status_code, 302)
        sub = EvidenceSubmission.objects.get(company=self.c)
        self.assertEqual(sub.company_id, self.c.id)
        self.assertEqual(sub.checklist_item_id, self.item.id)

    def test_audit_exception_does_not_break_upload(self):
        # Auditing (and, by extension, any extraction side-effect) must never crash the
        # upload response — the evidence record is still created.
        with mock.patch('compliance.evidence_extraction.record_evidence_audit',
                        side_effect=RuntimeError('boom')):
            resp = self._upload()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EvidenceSubmission.objects.filter(company=self.c).count(), 1)

    def test_storage_exception_does_not_500(self):
        with mock.patch.object(EvidenceSubmission.objects, 'create',
                               side_effect=OSError('disk full')):
            resp = self._upload()
        self.assertEqual(resp.status_code, 302)  # safe redirect, not a 500

    def test_view_link_uses_submission_id_not_item_id(self):
        self._upload()
        sub = EvidenceSubmission.objects.get(company=self.c)
        body = self.client.get(
            reverse('compliance:evidence_submission_list', args=[self.item.id])).content.decode()
        self.assertIn(reverse('compliance:evidence_submission_detail', args=[sub.id]), body)


class EvidenceDetailTenantTests(TestCase):
    def test_own_evidence_detail_returns_200(self):
        c, item, sub = _company_with_submission()
        self.client.force_login(_journey_user(c, email='owndet@x.com'))
        resp = self.client.get(reverse('compliance:evidence_submission_detail', args=[sub.id]))
        self.assertEqual(resp.status_code, 200)

    def test_other_company_evidence_detail_returns_404(self):
        # Tenant isolation: a different company can never see this submission. Denied via
        # a non-enumerable 404 — never a 200, never a crash, never reveals existence.
        c1, item1, sub1 = _company_with_submission()
        c2 = _company()
        self.client.force_login(_journey_user(c2, email='otherdet@x.com'))
        resp = self.client.get(reverse('compliance:evidence_submission_detail', args=[sub1.id]))
        self.assertEqual(resp.status_code, 404)

    def test_stale_evidence_id_returns_404_not_500(self):
        c = _company()
        self.client.force_login(_journey_user(c, email='staledet@x.com'))
        resp = self.client.get(reverse('compliance:evidence_submission_detail', args=[987654]))
        self.assertEqual(resp.status_code, 404)


class EvidenceScopeApprovalTests(TestCase):
    """Latest root cause: scopes exist but are not approved -> no plan/checklist."""

    def _pending_scope_company(self):
        from compliance.tests import _company_with_applicability
        from compliance.framework_scope import propose_framework_scopes
        from compliance.models import CompanyFrameworkScope
        c, fv = _company_with_applicability()
        propose_framework_scopes(c, apply=True)
        scope = CompanyFrameworkScope.objects.filter(company=c, status='proposed').first()
        return c, fv, scope

    def test_pending_scope_shows_pending_message_no_500(self):
        c, fv, scope = self._pending_scope_company()
        self.client.force_login(_journey_user(c, email='pendscope@x.com'))
        resp = self.client.get(reverse('compliance:evidence_checklist'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EvidenceChecklistItem.objects.filter(company=c).count(), 0)
        self.assertContains(resp, 'pending approval')

    def test_pending_scope_upload_is_safe_not_500(self):
        c, fv, scope = self._pending_scope_company()
        self.client.force_login(_journey_user(c, email='pendup@x.com'))
        # No checklist item exists -> any upload id is invalid -> safe redirect, never 500.
        resp = self.client.post(reverse('compliance:evidence_upload_v2', args=[123456]),
                                {'uploaded_file': _SUF('p.pdf', b'%PDF-1.4 ok')})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EvidenceSubmission.objects.filter(company=c).count(), 0)

    def test_approving_scope_generates_checklist(self):
        c, fv, scope = self._pending_scope_company()
        staff = _journey_user(c, email='scopestaff@x.com', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(EvidenceChecklistItem.objects.filter(company=c).count(), 0)
        self.client.post(reverse('compliance:approve_scope', args=[scope.id]))
        scope.refresh_from_db()
        self.assertEqual(scope.status, 'approved')
        # Approval chained the control plan + evidence checklist generation.
        self.assertTrue(EvidenceChecklistItem.objects.filter(company=c).exists())

    def test_upload_works_after_checklist_generated(self):
        c, fv, scope = self._pending_scope_company()
        staff = _journey_user(c, email='scopestaff2@x.com', is_staff=True)
        self.client.force_login(staff)
        self.client.post(reverse('compliance:approve_scope', args=[scope.id]))
        item = EvidenceChecklistItem.objects.filter(company=c).first()
        self.assertIsNotNone(item)
        # A company user can now upload against the generated checklist item.
        self.client.force_login(_journey_user(c, email='scopeup@x.com'))
        resp = self.client.post(reverse('compliance:evidence_upload_v2', args=[item.id]),
                                {'uploaded_file': _SUF('p.pdf', b'%PDF-1.4 ok'), 'notes': ''})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EvidenceSubmission.objects.filter(company=c).count(), 1)


# ============================================================
# EVIDENCE-UPLOAD-HOTFIX-A — both upload endpoints must never 500
# ============================================================
class EvidenceUploadNo500Tests(TestCase):
    def setUp(self):
        self.c, self.fv, self.scope = _company_with_checklist()
        self.item = EvidenceChecklistItem.objects.filter(company=self.c).first()
        self.control = self.item.evidence_requirement.control
        self.user = _journey_user(self.c, email='no500@x.com')
        self.client.force_login(self.user)

    # ---- Checklist (v2) endpoint ----
    def test_checklist_txt_upload_succeeds(self):
        resp = self.client.post(
            reverse('compliance:evidence_upload_v2', args=[self.item.id]),
            {'uploaded_file': _SUF('policy.txt', b'Access control policy approved.'), 'notes': ''})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EvidenceSubmission.objects.filter(company=self.c).count(), 1)

    def test_checklist_unsupported_type_no_500(self):
        resp = self.client.post(
            reverse('compliance:evidence_upload_v2', args=[self.item.id]),
            {'uploaded_file': _SUF('m.exe', b'MZ', content_type='application/octet-stream')})
        self.assertIn(resp.status_code, (200, 302))
        self.assertEqual(EvidenceSubmission.objects.filter(company=self.c).count(), 0)

    def test_checklist_missing_file_no_500(self):
        resp = self.client.post(reverse('compliance:evidence_upload_v2', args=[self.item.id]), {})
        self.assertIn(resp.status_code, (200, 302))
        self.assertEqual(EvidenceSubmission.objects.filter(company=self.c).count(), 0)

    def test_checklist_storage_failure_no_500(self):
        with mock.patch.object(EvidenceSubmission.objects, 'create',
                               side_effect=OSError('disk full')):
            resp = self.client.post(
                reverse('compliance:evidence_upload_v2', args=[self.item.id]),
                {'uploaded_file': _SUF('p.txt', b'x')})
        self.assertEqual(resp.status_code, 302)

    # ---- Control-detail (legacy) endpoint ----
    def test_control_txt_upload_succeeds(self):
        from compliance.models import Evidence
        resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                {'evidence_file': _SUF('policy.txt', b'Access control policy.')})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Evidence.objects.filter(company_control__company=self.c).count(), 1)

    def test_control_upload_no_500_when_celery_dispatch_succeeds(self):
        # Root-cause regression: the success path must not blow up on a shadowed gettext
        # alias, and must not leak an internal exception string to the user.
        with mock.patch('monitoring.tasks.analyze_evidence_async.delay', return_value=None):
            resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                    {'evidence_file': _SUF('p.txt', b'ok')}, follow=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn('object is not callable', body)
        self.assertNotIn('Error processing file:', body)

    def test_control_unsupported_type_no_500(self):
        from compliance.models import Evidence
        resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                {'evidence_file': _SUF('m.exe', b'MZ')})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Evidence.objects.filter(company_control__company=self.c).count(), 0)

    def test_control_missing_file_no_500(self):
        resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]), {})
        self.assertEqual(resp.status_code, 302)

    def test_control_storage_failure_no_500_no_path_leak(self):
        from compliance.models import Evidence
        with mock.patch.object(Evidence.objects, 'create', side_effect=OSError('/srv/media denied')):
            resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                    {'evidence_file': _SUF('p.txt', b'x')}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('/srv/media', resp.content.decode())      # no server path leaked

    def test_control_pipeline_failure_keeps_evidence_no_500(self):
        from compliance.models import Evidence
        with mock.patch('compliance.services.process_evidence_pipeline',
                        side_effect=RuntimeError('ocr boom')), \
             mock.patch('monitoring.tasks.analyze_evidence_async.delay',
                        side_effect=Exception('no broker')):
            resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                    {'evidence_file': _SUF('p.txt', b'x')}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('ocr boom', resp.content.decode())        # exception not exposed
        self.assertEqual(Evidence.objects.filter(company_control__company=self.c).count(), 1)

    def test_control_upload_without_company_is_safe(self):
        from core.models import User
        staff = User.objects.create_user(username='no500staff@x.com', email='no500staff@x.com',
                                         password='longenough12', role='admin', is_staff=True)
        self.client.force_login(staff)                             # staff has no company
        resp = self.client.post(reverse('compliance:upload_evidence', args=[self.control.id]),
                                {'evidence_file': _SUF('p.txt', b'x')})
        self.assertIn(resp.status_code, (302, 403))               # safe, never 500
