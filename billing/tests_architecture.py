from decimal import Decimal

from django.test import TestCase

from billing.event_services import mark_event_outcome, record_event
from billing.models import Payment, PaymentEvent
from core.models import Company


class PaymentEventInboxTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Payments Tenant', cr_number='9900000011', sector='technology', size='micro'
        )
        self.payment = Payment.objects.create(
            company=self.company, provider='moyasar', provider_payment_id='pay_architecture_1',
            amount=Decimal('99.00'), currency='SAR', status='pending',
        )
        self.payload = {
            'secret_token': 'must-not-be-persisted',
            'data': {'id': 'pay_architecture_1', 'status': 'paid', 'amount': 9900,
                     'currency': 'SAR', 'updated_at': '2026-08-16T00:00:00Z'},
        }

    def test_same_event_is_claimed_once_and_secret_is_not_stored(self):
        event, claimed = record_event('moyasar', self.payload, payment=self.payment,
                                      company=self.company, signature_verified=True)
        self.assertTrue(claimed)
        self.assertNotIn('secret_token', event.payload)
        duplicate, claimed_again = record_event('moyasar', self.payload, payment=self.payment,
                                                company=self.company, signature_verified=True)
        self.assertFalse(claimed_again)
        self.assertEqual(event.pk, duplicate.pk)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_deferred_event_can_be_reclaimed_without_changing_event(self):
        event, claimed = record_event('moyasar', self.payload, payment=self.payment,
                                      company=self.company, signature_verified=True)
        self.assertTrue(claimed)
        mark_event_outcome(event, status='deferred', error='provider unavailable')
        retried, claimed_retry = record_event('moyasar', self.payload, payment=self.payment,
                                              company=self.company, signature_verified=True)
        self.assertTrue(claimed_retry)
        self.assertEqual(event.pk, retried.pk)
        self.assertEqual(retried.processing.status, 'processing')

    def test_event_is_append_only(self):
        event, _ = record_event('moyasar', self.payload, payment=self.payment,
                                company=self.company, signature_verified=True)
        event.event_type = 'mutated'
        with self.assertRaises(RuntimeError):
            event.save()


class EntitlementFailClosedTests(TestCase):
    def test_missing_subscription_hard_blocks_metered_feature(self):
        from billing.access import check_feature_access
        company = Company.objects.create(
            name='No Subscription Tenant', cr_number='9900000012',
            sector='technology', size='micro',
        )
        result = check_feature_access(company, 'evidence_upload')
        self.assertFalse(result.allowed)
        self.assertTrue(result.blocks_view)
        self.assertEqual(result.reason_code, 'no_subscription')
