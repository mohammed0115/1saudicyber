"""P0-3: with no OPENAI_API_KEY every AI function degrades safely (no client, no 500).

External AI stays advisory-only — these safe returns never constitute a final verdict.
Pure/no-network: the empty-key guard returns before any OpenAI client is built.
"""
from django.test import SimpleTestCase, override_settings

from ai_engine.services import (
    ai_enabled, classify_company, analyze_evidence, generate_gap_analysis)


@override_settings(OPENAI_API_KEY='')
class AiDisabledSafeDegradationTests(SimpleTestCase):
    def test_ai_enabled_is_false_without_key(self):
        self.assertFalse(ai_enabled())

    def test_classify_company_returns_safe_result(self):
        r = classify_company({'name': 'X', 'sector': 'technology', 'size': 'small'})
        self.assertFalse(r['ai_available'])
        self.assertEqual(r['risk_level'], 'medium')

    def test_analyze_evidence_returns_insufficient(self):
        r = analyze_evidence('some evidence text', {
            'control_id': 'C-1', 'framework': 'NCA', 'title': 't', 'description': 'd'})
        self.assertFalse(r['ai_available'])
        self.assertEqual(r['verdict'], 'insufficient_evidence')   # never a final compliant verdict
        self.assertEqual(r['confidence'], 0.0)

    def test_generate_gap_analysis_returns_safe_zeroes(self):
        r = generate_gap_analysis({'name': 'X', 'sector': 'technology', 'size': 'small'}, {})
        self.assertFalse(r['ai_available'])
        self.assertEqual(r['compliance_score'], 0)


@override_settings(OPENAI_API_KEY='sk-test-not-real')
class AiEnabledFlagTests(SimpleTestCase):
    def test_ai_enabled_true_with_key(self):
        self.assertTrue(ai_enabled())
