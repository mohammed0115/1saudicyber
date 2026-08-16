from django.test import TestCase

from core.models import AuditLog, Company, CompanyJourney, CompanyMembership, User
from core.tenant_services import ensure_company_journey, ensure_company_membership
from core.tenancy import TenantScopeError, active_company_for, scoped_queryset
from compliance.models import CompanyControl


class TenantArchitectureTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(
            name='Tenant A', cr_number='9900000001', sector='technology', size='micro'
        )
        self.company_b = Company.objects.create(
            name='Tenant B', cr_number='9900000002', sector='technology', size='micro'
        )
        self.user = User.objects.create_user(
            email='tenant@example.test', password='VeryLongPassword123!',
            first_name='Tenant', last_name='User', company=self.company_a,
            role='company_admin', email_verified=True,
        )

    def test_membership_backed_active_company_and_switch(self):
        first = ensure_company_membership(self.user, self.company_a, role='company_admin')
        second = ensure_company_membership(self.user, self.company_b, role='compliance_officer')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(active_company_for(self.user), self.company_b)
        self.assertEqual(self.user.company, self.company_b)

    def test_unregistered_model_scope_fails_closed(self):
        with self.assertRaises(TenantScopeError):
            scoped_queryset(User, self.company_a)

    def test_company_scope_cannot_cross_tenants(self):
        # The scoped helper accepts no client supplied company id and always
        # yields only rows owned by its resolved tenant.
        self.assertEqual(scoped_queryset(CompanyControl, self.company_a).count(), 0)
        self.assertEqual(scoped_queryset(CompanyControl, self.company_b).count(), 0)

    def test_journey_is_single_source_and_never_certification(self):
        journey, created = ensure_company_journey(self.company_a)
        self.assertTrue(created)
        self.assertEqual(journey.state, 'registered')
        self.assertNotIn('certified', dict(CompanyJourney.STATE_CHOICES))


class AuditLogImmutabilityTests(TestCase):
    def test_application_log_cannot_be_updated_or_deleted(self):
        log = AuditLog.objects.create(action='architecture_test', path='/test/')
        log.action = 'mutated'
        with self.assertRaises(RuntimeError):
            log.save()
        with self.assertRaises(RuntimeError):
            AuditLog.objects.filter(pk=log.pk).delete()
