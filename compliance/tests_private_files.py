"""P0-01 — private, authorized file downloads (evidence + RFI attachments).

Two companies with real files. Proves: only an authorized principal (owner company, platform
admin, or an auditor with a LIVE accepted assignment) can download; everyone else gets 404;
the raw file is NOT reachable via a public /media/ URL; the stored path is never leaked; and a
hostile filename cannot break Content-Disposition. Content is read on allowed requests, not
just the status code.
"""
from django.test import TestCase
from django.urls import reverse

from compliance.models import EvidenceSubmission, Assessment
from compliance.tests import (_company_with_submission_file, _company_with_control,
                              _company, _journey_user, _assigned_auditor_user, _SUF)
from auditor_portal.tests import _company_control
from auditor_portal.models import DocumentRequest, CompanyRFIResponse
from auditors.tests import _auditor, _assignment
from core.models import User


def _read(resp):
    """Full body of a (streaming) FileResponse."""
    return b''.join(resp.streaming_content)


class EvidenceDownloadAccessTests(TestCase):
    def setUp(self):
        # Company A + its evidence file; Company B + its own evidence file (distinct CRs).
        self.a, self.item_a, self.sub_a = _company_with_submission_file(
            filename='policyA.txt', content=b'SECRET-A cybersecurity policy', file_type='txt')
        self.b, self.item_b, self.sub_b = _company_with_submission_file(
            filename='policyB.txt', content=b'SECRET-B cybersecurity policy', file_type='txt')
        self.url_a = reverse('compliance:download_evidence_file', args=[self.sub_a.id])
        self.url_b = reverse('compliance:download_evidence_file', args=[self.sub_b.id])

    # 1 — owner downloads its own file (and gets the real bytes)
    def test_owner_can_download_and_receives_content(self):
        self.client.force_login(_journey_user(self.a, email='ownerA@x.com'))
        resp = self.client.get(self.url_a)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_read(resp), b'SECRET-A cybersecurity policy')

    # 2 — a different company cannot read company A's file
    def test_other_company_user_gets_404(self):
        self.client.force_login(_journey_user(self.b, email='strangerB@x.com'))
        self.assertEqual(self.client.get(self.url_a).status_code, 404)

    # 3 — anonymous cannot download (login-gated; never the file)
    def test_anonymous_cannot_download(self):
        resp = self.client.get(self.url_a)
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('/login', resp.url)

    # 4 — a user with no company owns nothing
    def test_user_without_company_gets_404(self):
        u = User.objects.create_user(email='nocompany@x.com', password='longenough12')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url_a).status_code, 404)

    # 5 — an auditor with NO assignment to A cannot download
    def test_unassigned_auditor_gets_404(self):
        u, p = _auditor(status='active')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url_a).status_code, 404)

    # 6 — a PENDING (requested) assignment does not grant access
    def test_pending_auditor_gets_404(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='requested')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url_a).status_code, 404)

    # 7 — a cancelled/rejected assignment revokes access
    def test_cancelled_assignment_auditor_gets_404(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='cancelled')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url_a).status_code, 404)

    # 8 — a LIVE accepted auditor can download the company's evidence
    def test_accepted_auditor_can_download(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(self.url_a)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_read(resp), b'SECRET-A cybersecurity policy')

    # 9 — an auditor accepted for A cannot reach company B's evidence
    def test_auditor_of_a_cannot_download_b(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url_b).status_code, 404)

    # 10 — the raw file is NOT reachable via a public URL (private storage)
    def test_evidence_file_has_no_public_url(self):
        from django.conf import settings
        # base_url=None on the private local storage => .url is unavailable (fail-loud) ...
        with self.assertRaises(ValueError):
            _ = self.sub_a.uploaded_file.url
        # ... and the bytes live OUTSIDE MEDIA_ROOT, so /media/ (dev static or a proxy) can't serve them.
        self.assertTrue(str(self.sub_a.uploaded_file.path).startswith(str(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(str(self.sub_a.uploaded_file.path).startswith(str(settings.MEDIA_ROOT)))

    # 11 — the response never leaks the internal storage path
    def test_response_does_not_leak_internal_path(self):
        self.client.force_login(_journey_user(self.a, email='ownerA2@x.com'))
        resp = self.client.get(self.url_a)
        cd = resp.headers.get('Content-Disposition', '')
        self.assertIn('policyA.txt', cd)               # user-facing name only
        self.assertNotIn('private_media', cd)
        self.assertNotIn('evidence_v2', cd)

    # 12 — a hostile filename cannot break Content-Disposition / smuggle a path
    def test_special_char_filename_is_safe(self):
        sub = EvidenceSubmission.objects.create(
            company=self.a, checklist_item=self.item_a,
            uploaded_file=_SUF('weird.txt', b'x'),
            original_filename='../../etc/pa ss"wd\r\n.txt', file_type='txt', file_size=1)
        self.client.force_login(_journey_user(self.a, email='ownerA3@x.com'))
        resp = self.client.get(reverse('compliance:download_evidence_file', args=[sub.id]))
        self.assertEqual(resp.status_code, 200)
        cd = resp.headers.get('Content-Disposition', '')
        self.assertNotIn('\n', cd)                     # header not split
        self.assertNotIn('\r', cd)


class RfiAttachmentDownloadAccessTests(TestCase):
    """The RFI attachment was previously exposed as a raw {{ attachment.url }} (/media/…).
    It must now go through the authorized download view with the same tenant/engagement rules."""

    def setUp(self):
        self.a, self.ctl = _company_with_control()
        cc = _company_control(self.a, self.ctl)
        aud = _assigned_auditor_user(self.a, email='rfi_aud@x.com')   # active + accepted
        assessment = Assessment.objects.create(
            company=self.a, assigned_auditor=aud,
            assessment_type='formal_audit', status='auditor_review')
        dr = DocumentRequest.objects.create(assessment=assessment, company_control=cc,
                                            auditor=aud, description='need doc')
        self.rfi = CompanyRFIResponse.objects.create(
            request=dr, responder=_journey_user(self.a, email='rfi_resp@x.com'),
            response_text='here', attachment=_SUF('proof.pdf', b'%PDF-1.4 rfi-secret'))
        self.url = reverse('auditor_portal:download_rfi_attachment', args=[self.rfi.id])

    def test_owner_company_can_download(self):
        self.client.force_login(_journey_user(self.a, email='rfi_owner@x.com'))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_read(resp), b'%PDF-1.4 rfi-secret')

    def test_foreign_company_gets_404(self):
        other = _company(cr_number='9090909090')
        self.client.force_login(_journey_user(other, email='rfi_foreign@x.com'))
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_cancelled_auditor_gets_404(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='cancelled')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_template_links_to_protected_route_not_media(self):
        # The company RFI list must render the authorized URL and never a raw /media/ path.
        self.client.force_login(_journey_user(self.a, email='rfi_list@x.com'))
        body = self.client.get(reverse('auditor_portal:company_rfi_list')).content.decode()
        self.assertIn(reverse('auditor_portal:download_rfi_attachment', args=[self.rfi.id]), body)
        self.assertNotIn('/media/rfi_responses', body)
