"""UAT-COMPANY-INTAKE-CLASSIFICATION-FIX-A — regression tests.

Covers: CSCC only via explicit critical-systems signal; supplier frameworks only via explicit
supplier checkbox (never a stale dropdown); user-facing reasons are clean Arabic (no internal
labels); correct per-version framework display names.
"""
from django.test import TestCase

from core.models import Company
from compliance.models import (CompanyIntakeProfile, Framework, FrameworkVersion)
from compliance.smart_classification import classify_company
from compliance.framework_applicability import (
    _rule_cscc, _rule_sabic, _rule_aramco, _rule_nca_ecc, _rule_ccc, _rule_tcc, _rule_osmacc,
    DECISION_APPLICABLE, DECISION_NOT)
from compliance.forms import CompanyIntakeForm


def _company(**kw):
    n = Company.objects.count() + 1
    d = dict(name='Co', cr_number=f'{n:010d}', sector='technology', size='small',
             contact_email=f'c{n}@x.com')
    d.update(kw)
    return Company.objects.create(**d)


def _status_map(company):
    return {r.code: r.status for r in classify_company(company).recommendations}


def _indicated_codes(company):
    return {r.code for r in classify_company(company).indicated}


class CsccInclusionTests(TestCase):
    def test_cscc_not_proposed_without_explicit_critical_systems(self):
        # UAT-A: cloud + remote + social + Aramco + SABIC, but NOT critical systems.
        c = _company()
        CompanyIntakeProfile.objects.create(
            company=c, uses_cloud_services=True, has_remote_work=True,
            manages_official_social_media_accounts=True, works_with_aramco=True,
            works_with_sabic=True, is_critical_system_operator=False)
        p = CompanyIntakeProfile.objects.get(company=c)
        self.assertEqual(_status_map(c)['NCA-CSCC-1-2019'], 'not_indicated')
        self.assertNotIn('NCA-CSCC-1-2019', _indicated_codes(c))
        # framework_applicability agrees: CSCC not applicable.
        self.assertEqual(_rule_cscc(p, c)[0], DECISION_NOT)

    def test_cscc_proposed_when_critical_systems_selected(self):
        c = _company()
        p = CompanyIntakeProfile.objects.create(company=c, is_critical_system_operator=True)
        self.assertEqual(_status_map(c)['NCA-CSCC-1-2019'], 'recommended')
        self.assertEqual(_rule_cscc(p, c)[0], DECISION_APPLICABLE)

    def test_high_risk_sector_alone_does_not_pull_cscc(self):
        c = _company(sector='banking')   # high-risk sector, but no critical-systems signal
        CompanyIntakeProfile.objects.create(company=c, is_critical_system_operator=False)
        self.assertEqual(_status_map(c)['NCA-CSCC-1-2019'], 'not_indicated')


class SupplierSignalTests(TestCase):
    def test_sabic_not_proposed_when_unchecked_even_with_stale_category(self):
        c = _company(target_sabic=False)
        p = CompanyIntakeProfile.objects.create(company=c, works_with_sabic=False,
                                                sabic_supplier_type='SM')  # stale dropdown value
        self.assertEqual(_status_map(c)['SABIC-CYBERTRUST-1-0'], 'not_indicated')
        self.assertEqual(_rule_sabic(p, c)[0], DECISION_NOT)

    def test_aramco_not_proposed_when_unchecked_even_with_stale_classification(self):
        c = _company(target_aramco=False)
        p = CompanyIntakeProfile.objects.create(company=c, works_with_aramco=False,
                                                aramco_supplier_type='critical')  # stale value
        self.assertEqual(_status_map(c)['ARAMCO-SACS-002'], 'not_indicated')
        self.assertEqual(_rule_aramco(p, c)[0], DECISION_NOT)

    def test_form_clears_stale_supplier_types_when_unchecked(self):
        form = CompanyIntakeForm(data={'works_with_sabic': '', 'sabic_supplier_type': 'SM',
                                       'works_with_aramco': '', 'aramco_supplier_type': 'critical'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['sabic_supplier_type'], '')
        self.assertEqual(form.cleaned_data['aramco_supplier_type'], '')


class ReasonsAndNamesTests(TestCase):
    _INTERNAL = ['Legacy', 'legacy_checkbox', 'Rule Engine', 'is_critical_system_operator',
                 'works_with_sabic', 'works_with_aramco', 'target_sabic', 'target_nca']

    def test_reasons_do_not_expose_internal_labels(self):
        c = _company()
        CompanyIntakeProfile.objects.create(company=c, is_critical_system_operator=True,
                                            works_with_sabic=True, uses_cloud_services=True)
        p = CompanyIntakeProfile.objects.get(company=c)
        # smart_classification reasons
        for r in classify_company(c).recommendations:
            for bad in self._INTERNAL:
                self.assertNotIn(bad, r.reason_ar)
        # framework_applicability rule reasons (all rules, applicable + not-applicable branches)
        for rule in (_rule_nca_ecc, _rule_cscc, _rule_ccc, _rule_tcc, _rule_osmacc,
                     _rule_aramco, _rule_sabic):
            _, reason, _ = rule(p, c)
            for bad in self._INTERNAL:
                self.assertNotIn(bad, reason)

    def test_framework_display_names_are_correct(self):
        fw = Framework.objects.create(code='NCA', name='NCA Essential Cybersecurity Controls')
        expected = {
            'NCA-ECC-2-2024': 'الضوابط الأساسية للأمن السيبراني',
            'NCA-CCC-2-2024': 'ضوابط الحوسبة السحابية',
            'NCA-CSCC-1-2019': 'ضوابط الأنظمة الحساسة',
            'NCA-TCC-1-2021': 'ضوابط العمل عن بُعد',
            'NCA-OSMACC-1-2021': 'ضوابط حسابات التواصل الرسمية',
        }
        for code, name_ar in expected.items():
            fv = FrameworkVersion.objects.create(code=code, framework=fw, version_label=code)
            self.assertEqual(fv.display_name_ar, name_ar)      # NOT all "Essential..."
        # English names distinct too
        fv_ccc = FrameworkVersion.objects.get(code='NCA-CCC-2-2024')
        self.assertEqual(fv_ccc.display_name_en, 'NCA Cloud Cybersecurity Controls')


class RiskReasonTests(TestCase):
    def test_risk_reason_reflects_actual_signals(self):
        c = _company()
        CompanyIntakeProfile.objects.create(company=c, uses_cloud_services=True,
                                            has_remote_work=True, works_with_aramco=True)
        reason = classify_company(c).risk_reason_ar
        self.assertIn('سحابية', reason)
        self.assertIn('العمل عن بُعد', reason)
        self.assertIn('أرامكو', reason)


class ClassificationPageRenderTests(TestCase):
    def _login(self, c, email):
        from django.urls import reverse
        from compliance.tests import _journey_user
        self.client.force_login(_journey_user(c, email=email))

    def test_complete_uses_edit_cta_and_shows_risk_reason(self):
        from django.urls import reverse
        c = _company()
        CompanyIntakeProfile.objects.create(company=c, uses_cloud_services=True)
        self._login(c, 'ctac@x.com')
        body = self.client.get(reverse('compliance:classification')).content.decode()
        self.assertIn('تعديل بيانات التصنيف', body)          # complete -> edit, not "complete"
        self.assertNotIn('إكمال بيانات التصنيف', body)
        self.assertIn('ضوابط الحوسبة السحابية', body)        # CCC Arabic name (indicated)
        self.assertIn('تم تصنيف مستوى المخاطر', body)        # risk explanation present
        self.assertNotIn('ضوابط الأنظمة الحساسة', body)      # CSCC not-indicated -> hidden

    def test_incomplete_uses_complete_cta(self):
        from django.urls import reverse
        c = _company()   # no intake profile
        self._login(c, 'ctai@x.com')
        body = self.client.get(reverse('compliance:classification')).content.decode()
        self.assertIn('إكمال بيانات التصنيف', body)
        self.assertNotIn('تعديل بيانات التصنيف', body)
