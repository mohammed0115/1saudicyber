from django.core.exceptions import ValidationError
from django.test import TestCase

from compliance.models import CompanyControl, Control, Domain, Framework
from core.models import Company, User
from integrations.models import ControlTestDefinition, IntegrationConnection, IntegrationProvider
from integrations.services import execute_control_test, test_connection


class AutomatedControlTestingTests(TestCase):
    def setUp(self):
        framework = Framework.objects.create(code='INT_FW', name='Integration Framework')
        domain = Domain.objects.create(framework=framework, code='INT', name='Integration Domain')
        self.control = Control.objects.create(
            framework=framework, domain=domain, control_id='INT-1',
            title='Integration control', description='Test control.',
        )
        self.company = Company.objects.create(
            name='Integration Co', cr_number='7100000001', sector='technology', size='small',
            contact_email='integration@example.test', target_nca=True,
        )
        self.user = User.objects.create_user(
            email='integration-user@example.test', password='longenough12', company=self.company,
        )
        CompanyControl.objects.create(company=self.company, control=self.control)
        self.provider = IntegrationProvider.objects.create(
            key='mock', name='Mock Connector', auth_type='mock', is_active=True,
        )
        self.connection = IntegrationConnection.objects.create(
            company=self.company, provider=self.provider, name='Mock source', created_by=self.user,
            configuration={'simulate_healthy': True},
        )
        self.definition = ControlTestDefinition.objects.create(
            company=self.company, connection=self.connection, key='endpoint-health',
            name='Endpoint health test', parameters={'simulate_outcome': 'fail'}, created_by=self.user,
        )
        self.definition.controls.add(self.control)

    def test_mock_connection_and_failed_control_test_create_traceable_result(self):
        health = test_connection(self.connection)
        self.assertTrue(health['ok'])
        run = execute_control_test(self.definition, idempotency_key='manual-run-1')
        self.assertEqual(run.status, 'failed')
        result = run.results.get()
        self.assertEqual(result.outcome, 'fail')
        self.assertTrue(result.evidence_hash)
        self.assertTrue(result.evidence_uri.startswith('connector://mock/'))

    def test_idempotency_returns_original_run(self):
        test_connection(self.connection)
        first = execute_control_test(self.definition, idempotency_key='same-run')
        second = execute_control_test(self.definition, idempotency_key='same-run')
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.results.count(), 1)

    def test_connection_configuration_rejects_raw_secrets(self):
        unsafe = IntegrationConnection(
            company=self.company, provider=self.provider, name='Unsafe',
            configuration={'api_key': 'not-allowed'},
        )
        with self.assertRaises(ValidationError):
            unsafe.full_clean()
