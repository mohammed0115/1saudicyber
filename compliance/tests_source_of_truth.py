"""R3: advisory AI (Evidence path) is never authoritative — it must not overwrite a
human/compliance CompanyControl.status (single source of truth)."""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from compliance.tests import _company_with_control
from compliance.models import CompanyControl, Evidence
from compliance.services import process_evidence_pipeline, HUMAN_AUTHORITATIVE_STATUSES


def _evidence(cc):
    return Evidence.objects.create(
        company_control=cc, uploaded_by=None,
        file=SimpleUploadedFile('p.txt', b'policy text'), original_filename='p.txt',
        file_type='txt', file_size=11, status='processing')


class AiNeverOverwritesHumanStatusTests(TestCase):
    def _run_pipeline_returns_compliant_ai(self, cc):
        ev = _evidence(cc)
        with mock.patch('compliance.services.process_uploaded_file',
                        return_value={'text': 'policy text', 'confidence': 1.0, 'language': 'en'}), \
             mock.patch('compliance.services.analyze_evidence',
                        return_value={'verdict': 'compliant', 'confidence': 0.9,
                                      'reasoning_en': '', 'reasoning_ar': ''}):
            process_evidence_pipeline(ev.id)
        cc.refresh_from_db()
        return cc

    def test_ai_does_not_overwrite_human_compliant(self):
        c, control = _company_with_control()
        cc = CompanyControl.objects.get_or_create(company=c, control=control)[0]
        cc.status = 'compliant'          # human/compliance decision
        cc.save(update_fields=['status'])
        cc = self._run_pipeline_returns_compliant_ai(cc)
        self.assertEqual(cc.status, 'compliant')     # unchanged — AI is not authoritative

    def test_ai_does_not_overwrite_non_compliant(self):
        c, control = _company_with_control()
        cc = CompanyControl.objects.get_or_create(company=c, control=control)[0]
        cc.status = 'non_compliant'
        cc.save(update_fields=['status'])
        cc = self._run_pipeline_returns_compliant_ai(cc)
        self.assertEqual(cc.status, 'non_compliant')

    def test_ai_sets_reviewed_from_pre_decision_state(self):
        c, control = _company_with_control()
        cc = CompanyControl.objects.get_or_create(company=c, control=control)[0]
        cc.status = 'not_started'        # no human decision yet
        cc.save(update_fields=['status'])
        cc = self._run_pipeline_returns_compliant_ai(cc)
        self.assertEqual(cc.status, 'ai_reviewed')   # advisory state is allowed here

    def test_human_authoritative_set_is_final_states(self):
        self.assertEqual(HUMAN_AUTHORITATIVE_STATUSES,
                         {'compliant', 'non_compliant', 'partially_compliant', 'not_applicable'})
