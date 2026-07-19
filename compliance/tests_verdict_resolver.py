"""F-AUDIT A1 — tests for the read-only cross-silo auditor-verdict resolver."""
from django.test import TestCase

from compliance.models import ControlAssessment, Assessment, CompanyControl
from auditor_portal.models import AuditorControlVerdict
from compliance.verdict_resolver import (
    resolve_control_verdicts, company_verdict_disagreements)
from compliance.auditor_verdict import record_auditor_final_verdict
from compliance.tests import (_company_with_control, _company_with_submission,
                              _submission, _staff_user)


class VerdictResolverTests(TestCase):
    def test_single_silo_no_disagreement(self):
        c, ctl = _company_with_control()
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertEqual(e['canonical'], 'compliant')
        self.assertEqual(e['control_assessment'], 'compliant')
        self.assertFalse(e['has_disagreement'])

    def test_not_reviewed_is_not_a_decision(self):
        c, ctl = _company_with_control()
        ControlAssessment.objects.create(company=c, control=ctl, status='not_reviewed')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertIsNone(e['control_assessment'])   # 'not_reviewed' -> "no opinion"
        self.assertFalse(e['has_disagreement'])

    def test_disagreement_control_assessment_vs_final_verdict(self):
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        ctl = item.evidence_requirement.control
        record_auditor_final_verdict(sub, _staff_user(), status='final_nc', rationale='x')  # -> non_compliant
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertEqual(e['control_assessment'], 'compliant')
        self.assertEqual(e['auditor_final_verdict'], 'non_compliant')   # final_nc normalized
        self.assertEqual(e['canonical'], 'compliant')                   # ControlAssessment authoritative
        self.assertTrue(e['has_disagreement'])
        self.assertEqual(company_verdict_disagreements(c)[0]['control_id'], ctl.control_id)

    def test_auditor_control_verdict_mapped_and_agreement_is_not_conflict(self):
        c, ctl = _company_with_control()
        a = Assessment.objects.create(company=c, assessment_type='formal_audit')
        cc = CompanyControl.objects.create(company=c, control=ctl)
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc, status='compliant')
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertEqual(e['auditor_control_verdict'], 'compliant')
        self.assertFalse(e['has_disagreement'])          # both say compliant
        self.assertEqual(company_verdict_disagreements(c), [])

    def test_auditor_control_verdict_conflict_is_flagged(self):
        c, ctl = _company_with_control()
        a = Assessment.objects.create(company=c, assessment_type='formal_audit')
        cc = CompanyControl.objects.create(company=c, control=ctl)
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc, status='non_compliant')
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertTrue(e['has_disagreement'])
        self.assertEqual(e['distinct_decisions'], ['compliant', 'non_compliant'])

    def test_stale_final_verdict_excluded_from_resolution(self):
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        ctl = item.evidence_requirement.control
        record_auditor_final_verdict(sub, _staff_user(), status='final_nc', rationale='x')
        s2 = _submission(c, item, name='p2.txt'); s2.version = 2; s2.save(update_fields=['version'])
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        e = resolve_control_verdicts(c)[ctl.control_id]
        self.assertIsNone(e['auditor_final_verdict'])    # stale verdict is ignored (R2)
        self.assertFalse(e['has_disagreement'])          # only ControlAssessment has a live opinion

    def test_canonical_verdict_prefers_control_assessment(self):
        from compliance.verdict_resolver import canonical_verdict
        c, ctl = _company_with_control()
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        self.assertEqual(canonical_verdict(c, ctl.control_id), 'compliant')

    def test_canonical_verdict_falls_back_to_portal_verdict(self):
        from compliance.verdict_resolver import canonical_verdict
        c, ctl = _company_with_control()
        a = Assessment.objects.create(company=c, assessment_type='formal_audit')
        cc = CompanyControl.objects.create(company=c, control=ctl)
        AuditorControlVerdict.objects.create(assessment=a, company_control=cc, status='non_compliant')
        # No ControlAssessment -> canonical falls back to the auditor-portal verdict.
        self.assertEqual(canonical_verdict(c, ctl.control_id), 'non_compliant')

    def test_canonical_verdict_none_when_no_opinion(self):
        from compliance.verdict_resolver import canonical_verdict
        c, ctl = _company_with_control()
        self.assertIsNone(canonical_verdict(c, ctl.control_id))

    def test_read_only_writes_nothing(self):
        c, ctl = _company_with_control()
        ControlAssessment.objects.create(company=c, control=ctl, status='compliant')
        before = (ControlAssessment.objects.count(), AuditorControlVerdict.objects.count())
        resolve_control_verdicts(c)
        company_verdict_disagreements(c)
        after = (ControlAssessment.objects.count(), AuditorControlVerdict.objects.count())
        self.assertEqual(before, after)
