"""P1-6: data sovereignty — external LLM calls are fail-closed.

Even with a valid API key, evidence/company text must NOT be sent to an external LLM
unless AI_DATA_RESIDENCY_MODE=external is explicitly set (PDPL / NCA data classification).
"""
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ai_engine.services import (
    analyze_evidence, external_ai_allowed, ai_data_residency_mode)

_CONTROL = {'control_id': 'C-1', 'framework': 'NCA', 'title': 't', 'description': 'd'}


@override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
class ResidencyDisabledBlocksExternalTests(SimpleTestCase):
    def test_mode_and_flag(self):
        self.assertEqual(ai_data_residency_mode(), 'disabled')
        self.assertFalse(external_ai_allowed())          # key present but not opted in

    def test_evidence_text_never_leaves(self):
        with mock.patch('ai_engine.services.get_openai_client') as client:
            r = analyze_evidence('SECRET client evidence text', _CONTROL)
        client.assert_not_called()                       # no external call at all
        self.assertFalse(r['ai_available'])
        self.assertEqual(r['verdict'], 'insufficient_evidence')
        self.assertEqual(r['residency_mode'], 'disabled')


@override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='local')
class ResidencyLocalNotYetExternalTests(SimpleTestCase):
    def test_local_mode_does_not_call_external(self):
        with mock.patch('ai_engine.services.get_openai_client') as client:
            analyze_evidence('text', _CONTROL)
        client.assert_not_called()                       # 'local' adapter not wired -> no external


@override_settings(OPENAI_API_KEY='', AI_DATA_RESIDENCY_MODE='external')
class ResidencyExternalStillNeedsKeyTests(SimpleTestCase):
    def test_external_without_key_blocked(self):
        self.assertFalse(external_ai_allowed())


@override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
class ChecklistProviderResidencyTests(SimpleTestCase):
    """The checklist AI path (evidence_ai_analyzer) must obey the same residency gate."""
    def test_provider_blocked_when_residency_disabled(self):
        from compliance.evidence_ai_analyzer import OpenAIEvidenceProvider, ProviderUnavailable
        with self.assertRaises(ProviderUnavailable):
            OpenAIEvidenceProvider().analyze('some evidence prompt')   # no external call


@override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='external')
class ResidencyExternalOptInTests(SimpleTestCase):
    def test_opted_in_calls_external(self):
        self.assertTrue(external_ai_allowed())
        msg = mock.MagicMock()
        msg.message.content = '{"verdict": "compliant", "confidence": 0.9}'
        resp = mock.MagicMock()
        resp.choices = [msg]
        resp.usage.prompt_tokens = 1
        resp.usage.completion_tokens = 1
        fake = mock.MagicMock()
        fake.chat.completions.create.return_value = resp
        with mock.patch('ai_engine.services.get_openai_client', return_value=fake) as client:
            r = analyze_evidence('evidence text', _CONTROL)
        client.assert_called_once()                      # opted in -> external call happens
        self.assertEqual(r['verdict'], 'compliant')
