"""API tenant-isolation tests.

Regression for the evidence_analyze IDOR: an authenticated user must NOT be able to
trigger/read analysis of another company's Evidence via its id. IsAuthenticated proves
login only — the view must scope the Evidence to request.user.company.
"""
from unittest.mock import patch

from django.test import TestCase

from core.models import Company
from core.tests import make_framework_with_controls
from compliance.models import CompanyControl, Evidence


class EvidenceAnalyzeIsolationTests(TestCase):
    def _register(self, cr, email):
        payload = {'company_name': f'Co{cr}', 'cr_number': cr, 'sector': 'technology',
                   'size': 'small', 'email': email, 'password': 'longenough12',
                   'first_name': 'A', 'last_name': 'B', 'target_nca': True}
        r = self.client.post('/api/v1/register/', data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        company = Company.objects.get(cr_number=cr)
        auth = {'HTTP_AUTHORIZATION': f"Bearer {r.json()['access']}"}
        return company, auth

    def setUp(self):
        make_framework_with_controls('NCA_ECC', 2)
        self.company_a, self.auth_a = self._register('4444444444', 'owner@x.com')
        self.company_b, self.auth_b = self._register('5555555555', 'stranger@x.com')
        cc = CompanyControl.objects.filter(company=self.company_a).first()
        self.evidence = Evidence.objects.create(
            company_control=cc, uploaded_by=None, original_filename='a.pdf',
            file_type='pdf', file_size=8, status='uploaded')
        self.url = f'/api/v1/evidence/{self.evidence.id}/analyze/'

    def test_foreign_tenant_cannot_analyze_and_pipeline_never_runs(self):
        with patch('compliance.services.process_evidence_pipeline') as m:
            resp = self.client.post(self.url, **self.auth_b)
        self.assertEqual(resp.status_code, 404)     # IDOR closed: looks like "not found"
        m.assert_not_called()                       # foreign evidence is NEVER processed

    def test_owner_can_analyze_and_pipeline_runs_scoped(self):
        with patch('compliance.services.process_evidence_pipeline', return_value={'ok': True}) as m:
            resp = self.client.post(self.url, **self.auth_a)
        self.assertEqual(resp.status_code, 200)
        # P0-01 defense-in-depth: the owning company is forwarded to the pipeline.
        m.assert_called_once_with(self.evidence.id, expected_company_id=self.company_a.id)

    def test_anonymous_denied(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)


class ApiEndpointCoverageTests(TestCase):
    """DD-fix: broaden API coverage (was near-untested) — auth, tenant scope, JWT."""

    def _register(self, cr, email):
        payload = {'company_name': f'Co{cr}', 'cr_number': cr, 'sector': 'technology',
                   'size': 'small', 'email': email, 'password': 'longenough12',
                   'first_name': 'A', 'last_name': 'B', 'target_nca': True}
        r = self.client.post('/api/v1/register/', data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        return {'HTTP_AUTHORIZATION': f"Bearer {r.json()['access']}"}, r.json()

    def setUp(self):
        make_framework_with_controls('NCA_ECC', 3)
        self.auth, self.reg = self._register('6666666666', 'apicov@x.com')

    def test_controls_list_requires_auth(self):
        self.assertEqual(self.client.get('/api/v1/controls/').status_code, 401)

    def test_controls_list_returns_data_for_authed(self):
        r = self.client.get('/api/v1/controls/', **self.auth)
        self.assertEqual(r.status_code, 200)

    def test_control_detail_and_404(self):
        from compliance.models import Control
        cid = Control.objects.first().id
        self.assertEqual(self.client.get(f'/api/v1/controls/{cid}/', **self.auth).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/controls/99999/', **self.auth).status_code, 404)

    def test_classify_requires_auth(self):
        self.assertEqual(self.client.post('/api/v1/classify/').status_code, 401)

    def test_gap_analysis_requires_auth(self):
        self.assertEqual(self.client.get('/api/v1/gap-analysis/').status_code, 401)

    def test_dashboards_require_auth(self):
        for path in ('/api/v1/dashboard/executive/', '/api/v1/dashboard/compliance/',
                     '/api/v1/monitoring/scores/', '/api/v1/monitoring/alerts/'):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_dashboards_ok_for_authed(self):
        for path in ('/api/v1/dashboard/executive/', '/api/v1/dashboard/compliance/'):
            self.assertEqual(self.client.get(path, **self.auth).status_code, 200, path)

    def test_modern_endpoints_require_auth(self):
        for path in ('/api/v1/assessments/', '/api/v1/evidence-submissions/'):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_modern_endpoints_ok_and_tenant_scoped(self):
        # A freshly registered company has no ControlAssessment / EvidenceSubmission yet
        # (those are created by auditors / upload-v2), so each returns 200 with an empty list.
        for path in ('/api/v1/assessments/', '/api/v1/evidence-submissions/'):
            r = self.client.get(path, **self.auth)
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r.json(), [], path)

    def test_jwt_refresh_flow(self):
        r = self.client.post('/api/v1/token/refresh/',
                             data={'refresh': self.reg['refresh']}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.json())

    def test_register_rejects_bad_cr(self):
        r = self.client.post('/api/v1/register/', content_type='application/json',
                             data={'company_name': 'X', 'cr_number': 'abc', 'sector': 'technology',
                                   'size': 'small', 'email': 'bad@x.com', 'password': 'longenough12',
                                   'first_name': 'A', 'last_name': 'B', 'target_nca': True})
        self.assertEqual(r.status_code, 400)


class ApiUploadMagicByteTests(TestCase):
    """DD P1 — the API upload path must reject spoofed files by content (magic bytes),
    not just by extension + size (parity with the web upload paths)."""

    def _register(self, cr, email):
        payload = {'company_name': f'Co{cr}', 'cr_number': cr, 'sector': 'technology',
                   'size': 'small', 'email': email, 'password': 'longenough12',
                   'first_name': 'A', 'last_name': 'B', 'target_nca': True}
        r = self.client.post('/api/v1/register/', data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        return {'HTTP_AUTHORIZATION': f"Bearer {r.json()['access']}"}

    def setUp(self):
        from compliance.models import Control
        make_framework_with_controls('NCA_ECC', 2)
        self.auth = self._register('7777777777', 'upl@x.com')
        self.control_id = Control.objects.first().id

    def _upload(self, name, content):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            '/api/v1/evidence/upload/',
            data={'control_id': self.control_id,
                  'evidence_file': SimpleUploadedFile(name, content)},
            **self.auth)

    def test_spoofed_pdf_is_rejected(self):
        from compliance.models import Evidence
        with patch('compliance.services.process_evidence_pipeline') as m:
            resp = self._upload('evil.pdf', b'<html><script>alert(1)</script></html>')
        self.assertEqual(resp.status_code, 400)
        m.assert_not_called()                       # never stored / analysed
        self.assertEqual(Evidence.objects.count(), 0)

    def test_genuine_pdf_is_accepted(self):
        with patch('compliance.services.process_evidence_pipeline', return_value={'ok': True}):
            resp = self._upload('good.pdf', b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n')
        self.assertEqual(resp.status_code, 201, resp.content)
