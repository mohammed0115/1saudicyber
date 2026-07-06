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
        m.assert_called_once_with(self.evidence.id)

    def test_anonymous_denied(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)
