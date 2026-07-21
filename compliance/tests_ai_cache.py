"""AI advisory result caching — a re-analysis with unchanged inputs must NOT pay for
another model call (the expensive `_run_ai`). Any input change invalidates the cache.

Additive, advisory-only: caching never changes a compliance decision, never accepts/
rejects evidence. Uses the proven compliance submission fixtures with `_run_ai` mocked.
"""
from unittest import mock

from django.test import TestCase, override_settings

from compliance import evidence_analysis
from compliance.tests import _company_with_submission_file


_FAKE_AI = {
    'summary': 'ملخص استشاري', 'requirement_match': 'يغطي المتطلب جزئيًا',
    'potential_gaps': 'لا يوجد', 'confidence': 0.8, 'risk_flags': [],
}


@override_settings(OPENAI_API_KEY='test-key')
class AiAdvisoryCacheTests(TestCase):
    def setUp(self):
        # A .txt submission extracts text without OCR, so `text` is non-empty and stable.
        self.c, self.item, self.sub = _company_with_submission_file(
            filename='policy.txt', content=b'Access control policy approved and enforced.')

    def test_second_analysis_with_same_inputs_is_cached(self):
        with mock.patch.object(evidence_analysis, '_run_ai',
                               return_value=(_FAKE_AI, '', 'gpt-4o', 'openai')) as m:
            first = evidence_analysis.analyze_evidence_submission(self.sub, apply=True)
            second = evidence_analysis.analyze_evidence_submission(self.sub, apply=True)
        self.assertEqual(first['status'], 'completed')
        self.assertTrue(second.get('cached'))
        self.assertEqual(second['id'], first['id'])
        # The model was called exactly once across two analyses.
        self.assertEqual(m.call_count, 1)

    def test_cache_is_invalidated_when_extracted_text_changes(self):
        with mock.patch.object(evidence_analysis, '_run_ai',
                               return_value=(_FAKE_AI, '', 'gpt-4o', 'openai')) as m:
            evidence_analysis.analyze_evidence_submission(self.sub, apply=True)
            # Simulate different extracted text -> fingerprint changes -> AI runs again.
            with mock.patch.object(evidence_analysis, 'extract_text_from_submission',
                                   return_value=('completely different evidence body', False, '')):
                res = evidence_analysis.analyze_evidence_submission(self.sub, apply=True)
        self.assertFalse(res.get('cached'))
        self.assertEqual(m.call_count, 2)
