"""P0-04 — external AI data residency is FAIL-CLOSED at the provider boundary.

Tenant evidence must NOT reach an external LLM unless the CENTRAL residency policy
(external_ai_allowed) explicitly allows it. Key presence alone is NOT authorization, and
unknown / missing / malformed configuration fails closed. The specific vulnerability was
compliance/evidence_analysis._run_ai, which gated only on key presence.

Every test mocks or gates the provider boundary — none makes a real network call.
"""
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from ai_engine.services import external_ai_allowed, get_openai_client, ExternalAINotAllowed
from compliance import evidence_analysis

_CTL = SimpleNamespace(control_id='C-1', title='Access Control', description='requires MFA')
_REQ = SimpleNamespace(title='MFA policy', description='provide the MFA policy document')
_SECRET = 'TOP-SECRET-TENANT evidence body that must never leave the Kingdom'


def _fake_client_returning(json_str):
    msg = mock.MagicMock(); msg.message.content = json_str
    resp = mock.MagicMock(); resp.choices = [msg]
    fake = mock.MagicMock(); fake.chat.completions.create.return_value = resp
    return fake


# ---- §4/§12 — the central policy denies for anything other than an explicit 'external' opt-in ----
class PolicyFailClosedTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_disabled_with_key_denies(self):
        self.assertFalse(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='external')
    def test_external_with_key_allows(self):
        self.assertTrue(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='EXTERNAL')
    def test_external_case_insensitive_allows(self):
        self.assertTrue(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='')
    def test_empty_mode_denies(self):
        self.assertFalse(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE=None)
    def test_missing_none_mode_denies(self):
        self.assertFalse(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='local')
    def test_local_mode_denies(self):
        self.assertFalse(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='extrenal')
    def test_unknown_typo_mode_denies(self):
        self.assertFalse(external_ai_allowed())

    @override_settings(OPENAI_API_KEY='', AI_DATA_RESIDENCY_MODE='external')
    def test_external_without_key_denies(self):
        self.assertFalse(external_ai_allowed())


# ---- §6/§17 — the shared client factory is a fail-closed tripwire ----
class GetClientTripwireTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_factory_fails_closed_when_disabled(self):
        with self.assertRaises(ExternalAINotAllowed):
            get_openai_client()

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='extrenal')
    def test_factory_fails_closed_on_unknown_mode(self):
        with self.assertRaises(ExternalAINotAllowed):
            get_openai_client()

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='external')
    def test_factory_builds_when_allowed(self):
        self.assertIsNotNone(get_openai_client())   # network-free construction

    @override_settings(OPENAI_API_KEY='', AI_DATA_RESIDENCY_MODE='external')
    def test_public_reference_still_needs_key(self):
        with self.assertRaises(ExternalAINotAllowed):
            get_openai_client(allow_public_reference=True)

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_public_reference_exemption_is_narrow_and_explicit(self):
        # The ONE documented exception (public regulatory text, not tenant data) with a key.
        self.assertIsNotNone(get_openai_client(allow_public_reference=True))


# ---- §5/§15 — the fixed vulnerable path (_run_ai) ----
class RunAiFailClosedTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_run_ai_denied_builds_no_client_and_sends_nothing(self):
        with mock.patch('ai_engine.services.get_openai_client') as factory:
            data, err, model, provider = evidence_analysis._run_ai(_CTL, _REQ, _SECRET)
        factory.assert_not_called()             # no client constructed -> no egress at all
        self.assertIsNone(data)                 # safe: no advisory data
        self.assertIn('residency', err)

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='external')
    def test_run_ai_allowed_sends_once_with_evidence(self):
        fake = _fake_client_returning('{"summary": "ok", "confidence": 0.5}')
        with mock.patch('ai_engine.services.get_openai_client', return_value=fake) as factory:
            data, err, model, provider = evidence_analysis._run_ai(_CTL, _REQ, _SECRET)
        factory.assert_called_once()
        fake.chat.completions.create.assert_called_once()
        sent = fake.chat.completions.create.call_args.kwargs['messages'][1]['content']
        self.assertIn(_SECRET, sent)            # positive control: evidence IS sent when allowed
        self.assertEqual(data.get('summary'), 'ok')

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='external')
    def test_provider_failure_is_safe_no_fabricated_verdict(self):
        fake = mock.MagicMock()
        fake.chat.completions.create.side_effect = RuntimeError('provider down')
        with mock.patch('ai_engine.services.get_openai_client', return_value=fake):
            data, err, model, provider = evidence_analysis._run_ai(_CTL, _REQ, _SECRET)
        self.assertIsNone(data)                 # empty result is NOT interpreted as compliant
        self.assertIn('AI error', err)

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_run_ai_survives_forgotten_guard_via_tripwire(self):
        # Defense-in-depth: even if the explicit guard were bypassed, the real factory tripwire
        # (not mocked here) makes construction raise ExternalAINotAllowed -> safe result.
        data, err, model, provider = evidence_analysis._run_ai(_CTL, _REQ, _SECRET)
        self.assertIsNone(data)
        self.assertIn('residency', err)


# ---- §5/§7/§8 — integration: execution-time enforcement + advisory-only, never a compliance pass ----
class AnalyzeSubmissionResidencyTests(TestCase):
    def setUp(self):
        from compliance.tests import _company_with_submission_file
        self.company, self.item, self.sub = _company_with_submission_file(
            filename='policy.txt', content=b'SECRET tenant evidence text', file_type='txt')

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_execution_time_denied_needs_human_review_not_compliant(self):
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        with mock.patch('ai_engine.services.get_openai_client') as factory:
            analyze_evidence_submission(self.sub, apply=True)
        factory.assert_not_called()
        res = EvidenceAnalysisResult.objects.get(evidence_submission=self.sub)
        self.assertEqual(res.status, 'needs_human_review')   # AI denied != compliance approved
        self.assertIsNone(res.confidence)

    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_management_command_is_not_a_residency_backdoor(self):
        from compliance.models import EvidenceAnalysisResult
        with mock.patch('ai_engine.services.get_openai_client') as factory:
            call_command('analyze_evidence_submission', submission_id=self.sub.id,
                         apply=True, stdout=StringIO())
        factory.assert_not_called()
        res = EvidenceAnalysisResult.objects.get(evidence_submission=self.sub)
        self.assertEqual(res.status, 'needs_human_review')


# ---- §9 — the Celery-reachable path (analyze_evidence) enforces at execution, not enqueue ----
class CeleryReachablePathTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_analyze_evidence_denied_at_execution_time(self):
        from ai_engine.services import analyze_evidence
        control = {'control_id': 'C-1', 'framework': 'NCA', 'title': 't', 'description': 'd'}
        with mock.patch('ai_engine.services.get_openai_client') as factory:
            r = analyze_evidence('SECRET evidence text', control)
        factory.assert_not_called()             # worker re-checks policy when it runs the task
        self.assertFalse(r['ai_available'])
