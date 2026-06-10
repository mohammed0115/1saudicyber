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

    def test_one_row_per_targeted_framework(self):
        fake = {'compliance_score': 40, 'overall_risk_score': 60, 'critical_gaps': [],
                'top_priorities_en': [], 'predicted_audit_outcome_en': 'x',
                'predicted_audit_outcome_ar': 'x'}
        with mock.patch('ai_engine.views.generate_gap_analysis', return_value=fake):
            resp = self.client.get('/ai/gap-analysis/')
        self.assertEqual(resp.status_code, 200)

        rows = {g.framework_code: g for g in GapAnalysis.objects.filter(company=self.company)}
        # Two targeted frameworks -> exactly two rows (the bug saved only NCA).
        self.assertEqual(set(rows), {'NCA_ECC', 'ARAMCO_SACS002'})
        # Per-framework counts are real, not shared.
        self.assertEqual(rows['NCA_ECC'].total_controls, 3)
        self.assertEqual(rows['NCA_ECC'].compliant_count, 2)
        self.assertAlmostEqual(rows['NCA_ECC'].compliance_score, 2 / 3 * 100, places=1)
        self.assertEqual(rows['ARAMCO_SACS002'].total_controls, 2)
        self.assertEqual(rows['ARAMCO_SACS002'].compliant_count, 0)
        self.assertEqual(rows['ARAMCO_SACS002'].compliance_score, 0.0)
