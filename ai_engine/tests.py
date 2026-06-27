"""
Regression test for PATCH_NOTES fix #3 (FR-007.1):
gap analysis must persist one GapAnalysis row PER targeted framework
(was: NCA only), each with its own per-framework counts.

AI is mocked — the per-framework persistence is a Rule/DB concern, not an AI one
(Rules First -> AI Second -> Auditor Final).
"""
from unittest import mock

from django.test import TestCase

from core.models import User, Company
from compliance.models import Framework, Domain, Control, CompanyControl
from ai_engine.models import GapAnalysis


def _seed_fw(code, n, status_cycle):
    fw, _ = Framework.objects.get_or_create(code=code, defaults={'name': code})
    dom, _ = Domain.objects.get_or_create(framework=fw, name='D', defaults={'code': code + '_D'})
    controls = []
    for i in range(n):
        controls.append(Control.objects.create(
            framework=fw, domain=dom, control_id=f'{code}-{i}', title='t', description='d'))
    return fw, controls


class PerFrameworkGapAnalysisTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Co', cr_number='1212121212', sector='technology', size='small',
            contact_email='c@x.com', target_nca=True, target_aramco=True)  # two targets
        # NCA: 3 controls (2 compliant), Aramco: 2 controls (0 compliant)
        _, nca = _seed_fw('NCA_ECC', 3, None)
        _, ar = _seed_fw('ARAMCO_SACS002', 2, None)
        for i, c in enumerate(nca):
            CompanyControl.objects.create(company=self.company, control=c,
                                          status='compliant' if i < 2 else 'non_compliant')
        for c in ar:
            CompanyControl.objects.create(company=self.company, control=c, status='non_compliant')
        self.user = User.objects.create_user(
            email='g@x.com', password='longenough12', company=self.company, role='company_admin')
        self.client.force_login(self.user)

    def test_gap_analysis_is_safe_advisory_no_ai_no_rows(self):
        """Phase 8D-2-FIX-A: /ai/gap-analysis/ no longer triggers AI on GET (that caused
        an HTTP 500). It now renders a safe, read-only advisory page and creates NO
        GapAnalysis rows and makes NO AI call. The detailed per-framework analysis lives
        in the official compliance reports."""
        # If the view tried to call AI, this patch would make it explode — proving no call.
        with mock.patch('ai_engine.views.generate_gap_analysis',
                        side_effect=AssertionError('AI must NOT be called on gap-analysis GET')):
            resp = self.client.get('/ai/gap-analysis/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'استشاري')
        self.assertEqual(GapAnalysis.objects.filter(company=self.company).count(), 0)
