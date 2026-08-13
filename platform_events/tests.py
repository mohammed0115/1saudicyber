from django.core.exceptions import ValidationError
from django.test import TestCase

from compliance.models import CompanyControl, Control, Domain, Framework
from core.models import Company, User
from integrations.models import ControlTestDefinition, IntegrationConnection, IntegrationProvider
from integrations.services import execute_control_test, test_connection
from monitoring.models import Alert
from platform_events.models import DomainEvent, WebhookSubscription
from platform_events.services import review_status_recommendation


class PlatformEventTests(TestCase):
    def setUp(self):
        framework = Framework.objects.create(code='EVT_FW', name='Event Framework')
        domain = Domain.objects.create(framework=framework, code='EVT', name='Event Domain')
        self.control = Control.objects.create(
            framework=framework, domain=domain, control_id='EVT-1',
            title='Event control', description='Test control.',
        )
        self.company = Company.objects.create(
            name='Event Co', cr_number='7200000001', sector='technology', size='small',
            contact_email='event@example.test', target_nca=True,
        )
        self.user = User.objects.create_user(
            email='event-reviewer@example.test', password='longenough12',
            company=self.company, role='compliance_officer',
        )
        self.company_control = CompanyControl.objects.create(company=self.company, control=self.control)
        provider = IntegrationProvider.objects.create(key='mock', name='Mock', auth_type='mock')
        connection = IntegrationConnection.objects.create(
            company=self.company, provider=provider, name='Mock event source',
            configuration={'simulate_healthy': True},
        )
        self.definition = ControlTestDefinition.objects.create(
            company=self.company, connection=connection, key='event-test', name='Event test',
            parameters={'simulate_outcome': 'fail'},
        )
        self.definition.controls.add(self.control)
        test_connection(connection)

    def test_failed_test_generates_event_alert_and_reviewable_recommendation(self):
        run = execute_control_test(self.definition, idempotency_key='event-test-run')
        self.assertEqual(run.status, 'failed')
        self.assertEqual(DomainEvent.objects.filter(company=self.company, event_type='control.test.completed').count(), 1)
        self.assertEqual(Alert.objects.filter(company=self.company, affected_control='EVT-1').count(), 1)
        recommendation = run.results.get().status_recommendation
        self.assertEqual(recommendation.status, 'pending')
        review_status_recommendation(recommendation, reviewer=self.user, accept=True)
        self.company_control.refresh_from_db()
        self.assertEqual(self.company_control.status, 'non_compliant')

    def test_webhook_subscription_rejects_non_https_destination(self):
        subscription = WebhookSubscription(
            company=self.company, name='Unsafe', url='http://example.test/hook', event_types=['control.test.completed'],
        )
        with self.assertRaises(ValidationError):
            subscription.full_clean()
