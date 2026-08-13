from django.test import TestCase
from django.utils import timezone

from compliance.models import Control, Domain, Framework
from policy_engine.models import PolicyPack, PolicyVersion
from policy_engine.services import evaluate_policy


class PolicyEvaluationTests(TestCase):
    def setUp(self):
        framework = Framework.objects.create(code='TEST_FW', name='Test Framework')
        domain = Domain.objects.create(framework=framework, code='TEST', name='Test Domain')
        self.control = Control.objects.create(
            framework=framework,
            domain=domain,
            control_id='TEST-1',
            title='Test control',
            description='A test control.',
        )
        self.pack = PolicyPack.objects.create(key='ksa-test', name='KSA Test Rules')
        self.version = PolicyVersion.objects.create(
            policy_pack=self.pack,
            version='2026.1',
            status='approved',
            effective_from=timezone.localdate(),
            rules=[
                {
                    'id': 'government-controls',
                    'all': [{'field': 'sector', 'equals': 'government'}],
                    'include_control_ids': ['TEST-1', 'UNKNOWN-1'],
                    'reason': 'Government organisations require the test control.',
                },
            ],
        )

    def test_effective_policy_evaluation_is_reproducible(self):
        result = evaluate_policy(self.version, {'sector': 'government'})
        self.assertEqual(result['policy_pack'], 'ksa-test')
        self.assertEqual(result['policy_version'], '2026.1')
        self.assertEqual(result['applicable_controls'][0]['control_id'], 'TEST-1')
        self.assertEqual(result['unresolved_control_ids'], ['UNKNOWN-1'])
        self.assertTrue(result['evaluation_id'])
        self.assertTrue(result['decision_hash'])
        self.assertEqual(self.version.evaluations.count(), 1)

    def test_non_matching_subject_has_no_applicable_controls(self):
        result = evaluate_policy(self.version, {'sector': 'retail'})
        self.assertEqual(result['matched_rules'], [])
        self.assertEqual(result['applicable_controls'], [])

    def test_draft_policy_cannot_be_evaluated(self):
        draft = PolicyVersion.objects.create(
            policy_pack=self.pack,
            version='2026.2-draft',
            status='draft',
            rules=[],
        )
        with self.assertRaisesMessage(ValueError, 'not approved and effective'):
            evaluate_policy(draft, {'sector': 'government'})
