"""UAT-COMPANY-CLASSIFICATION-LOGIC-FIX-A — count / engine-agreement / scope / isolation.

Builds on tests_intake_classification.py. Verifies:
  #3 expected-control count reflects only the final (indicated) frameworks, CSCC counted once;
  #5 the smart-classification (classification page) and framework_applicability (review page)
     engines agree on the applicable framework set;
  #8 proposed scope excludes non-applicable frameworks (CSCC/SABIC/Aramco) and never duplicates;
  isolation: classification views are scoped to the authenticated user's own company.
"""
from django.test import TestCase
from django.urls import reverse

from core.models import Company, User
from compliance.models import (CompanyIntakeProfile, Framework, FrameworkVersion,
                               FrameworkApplicabilityResult, CompanyFrameworkScope)
from compliance.smart_classification import classify_company, official_control_count
from compliance.framework_applicability import (
    _rule_nca_ecc, _rule_cscc, _rule_ccc, _rule_tcc, _rule_osmacc, _rule_aramco, _rule_sabic,
    DECISION_APPLICABLE)
from compliance.framework_scope import propose_framework_scopes

_RULES = {
    'NCA-ECC-2-2024': _rule_nca_ecc, 'NCA-CSCC-1-2019': _rule_cscc, 'NCA-CCC-2-2024': _rule_ccc,
    'NCA-TCC-1-2021': _rule_tcc, 'NCA-OSMACC-1-2021': _rule_osmacc,
    'ARAMCO-SACS-002': _rule_aramco, 'SABIC-CYBERTRUST-1-0': _rule_sabic,
}


def _company(**kw):
    n = Company.objects.count() + 1
    d = dict(name='Co', cr_number=f'{n:010d}', sector='technology', size='small',
             contact_email=f'c{n}@x.com')
    d.update(kw)
    return Company.objects.create(**d)


def _scenario_A(c):
    # cloud + remote + social + Aramco + SABIC, but NOT critical systems.
    return CompanyIntakeProfile.objects.create(
        company=c, uses_cloud_services=True, has_remote_work=True,
        manages_official_social_media_accounts=True, works_with_aramco=True,
        works_with_sabic=True, is_critical_system_operator=False)


def _sc_indicated(c):
    return {r.code for r in classify_company(c).indicated}


def _fa_applicable(c):
    p = getattr(c, 'intake_profile', None)
    return {code for code, rule in _RULES.items() if rule(p, c)[0] == DECISION_APPLICABLE}


class ExpectedControlCountTests(TestCase):
    def test_count_excludes_cscc_when_not_critical(self):
        c = _company(); _scenario_A(c)
        result = classify_company(c)
        codes = {r.code for r in result.indicated}
        self.assertNotIn('NCA-CSCC-1-2019', codes)
        # total equals the sum of indicated frameworks only, and excludes CSCC's count.
        self.assertEqual(result.total_expected_controls,
                         sum(r.control_count for r in result.indicated))
        self.assertNotIn(official_control_count('NCA-CSCC-1-2019'),
                         [r.control_count for r in result.indicated if r.code == 'NCA-CSCC-1-2019'])

    def test_count_includes_cscc_once_when_critical(self):
        c = _company()
        CompanyIntakeProfile.objects.create(company=c, is_critical_system_operator=True)
        result = classify_company(c)
        cscc = [r for r in result.indicated if r.code == 'NCA-CSCC-1-2019']
        self.assertEqual(len(cscc), 1)                       # counted exactly once
        self.assertEqual(cscc[0].control_count, official_control_count('NCA-CSCC-1-2019'))


class EngineAgreementTests(TestCase):
    def test_both_engines_agree_and_exclude_cscc_scenario_A(self):
        c = _company(); _scenario_A(c)
        sc, fa = _sc_indicated(c), _fa_applicable(c)
        self.assertNotIn('NCA-CSCC-1-2019', sc)
        self.assertNotIn('NCA-CSCC-1-2019', fa)
        self.assertEqual(sc, fa)                              # same framework set

    def test_both_engines_agree_when_critical(self):
        c = _company()
        CompanyIntakeProfile.objects.create(company=c, is_critical_system_operator=True,
                                            uses_cloud_services=True)
        self.assertEqual(_sc_indicated(c), _fa_applicable(c))
        self.assertIn('NCA-CSCC-1-2019', _sc_indicated(c))


class ProposedScopeTests(TestCase):
    def setUp(self):
        self.c = _company()
        self.fw = Framework.objects.create(code='NCA', name='NCA')
        self.ecc = FrameworkVersion.objects.create(code='NCA-ECC-2-2024', framework=self.fw)
        self.cscc = FrameworkVersion.objects.create(code='NCA-CSCC-1-2019', framework=self.fw)

    def _far(self, fv, decision):
        FrameworkApplicabilityResult.objects.create(
            company=self.c, framework_version=fv, decision=decision, reason='x')

    def test_scope_excludes_not_applicable_cscc_and_no_duplicates(self):
        self._far(self.ecc, 'applicable')
        self._far(self.cscc, 'not_applicable')
        propose_framework_scopes(self.c, apply=True)
        propose_framework_scopes(self.c, apply=True)          # idempotent (run twice)
        scoped = set(CompanyFrameworkScope.objects.filter(company=self.c)
                     .values_list('framework_version__code', flat=True))
        self.assertIn('NCA-ECC-2-2024', scoped)
        self.assertNotIn('NCA-CSCC-1-2019', scoped)           # not proposed
        # no duplicate framework rows (unique_together also guarantees this)
        self.assertEqual(CompanyFrameworkScope.objects.filter(
            company=self.c, framework_version=self.ecc).count(), 1)


class ClassificationIsolationTests(TestCase):
    def test_classification_view_scoped_to_own_company(self):
        a = _company(name='A'); _scenario_A(a)
        b = _company(name='B')
        CompanyIntakeProfile.objects.create(company=b, is_critical_system_operator=True)
        ua = User.objects.create_user(email='ua@x.com', password='longenough12', company=a)
        self.client.force_login(ua)
        body = self.client.get(reverse('compliance:classification')).content.decode()
        # A user sees A's classification (no CSCC); there is no way to request B's (views use
        # request.user.company only — no company_id parameter).
        self.assertIn('ضوابط الحوسبة السحابية', body)         # A's CCC (cloud)
        self.assertNotIn('ضوابط الأنظمة الحساسة', body)       # B's CSCC must not leak to A
