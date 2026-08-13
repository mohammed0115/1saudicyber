from django.test import TestCase
from django.utils import timezone

from compliance.models import CompanyControl, Control, Domain, Evidence, Framework
from core.models import Company, User
from policy_engine.models import PolicyPack, PolicyVersion


class TenantScopedApiTests(TestCase):
    def setUp(self):
        framework = Framework.objects.create(code='API_FW', name='API Framework')
        domain = Domain.objects.create(framework=framework, code='API', name='API Domain')
        self.control = Control.objects.create(
            framework=framework,
            domain=domain,
            control_id='API-1',
            title='API control',
            description='Test control.',
        )
        self.company_a = Company.objects.create(
            name='Company A', cr_number='7000000001', sector='government', size='large',
            contact_email='a@example.test', target_nca=True,
        )
        self.company_b = Company.objects.create(
            name='Company B', cr_number='7000000002', sector='technology', size='small',
            contact_email='b@example.test', target_nca=True,
        )
        self.user_a = User.objects.create_user(
            email='a-user@example.test', password='longenough12', company=self.company_a,
        )
        self.control_a = CompanyControl.objects.create(company=self.company_a, control=self.control)
        self.control_b = CompanyControl.objects.create(company=self.company_b, control=self.control)
        self.client.force_login(self.user_a)

    def test_cannot_read_control_not_applicable_to_tenant(self):
        other_control = Control.objects.create(
            framework=self.control.framework,
            domain=self.control.domain,
            control_id='API-2', title='Other control', description='Other test control.',
        )
        CompanyControl.objects.create(company=self.company_b, control=other_control)
        response = self.client.get(f'/api/v1/controls/{other_control.id}/')
        self.assertEqual(response.status_code, 404)

    def test_cannot_analyse_another_tenant_evidence(self):
        evidence = Evidence.objects.create(
            company_control=self.control_b,
            uploaded_by=self.user_a,
            file='evidence/test.txt', original_filename='test.txt', file_type='txt', file_size=1,
        )
        response = self.client.post(f'/api/v1/evidence/{evidence.id}/analyze/')
        self.assertEqual(response.status_code, 403)

    def test_company_can_evaluate_published_policy(self):
        pack = PolicyPack.objects.create(key='api-policy', name='API Policy', status='active')
        version = PolicyVersion.objects.create(
            policy_pack=pack,
            version='1.0',
            status='approved',
            effective_from=timezone.localdate(),
            rules=[{
                'id': 'gov',
                'all': [{'field': 'sector', 'equals': 'government'}],
                'include_control_ids': ['API-1'],
                'reason': 'Government scope.',
            }],
        )
        response = self.client.post(
            '/api/v1/platform/policy-evaluations/',
            data={'policy_version_id': version.id}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['applicable_controls'][0]['control_id'], 'API-1')


class PlatformOperationalApiTests(TestCase):
    def test_health_is_low_disclosure_and_returns_correlation_headers(self):
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok'})
        self.assertTrue(response['X-Request-ID'])
        self.assertTrue(response['X-Response-Time-ms'])

    def test_capabilities_requires_authentication(self):
        response = self.client.get('/api/v1/platform/capabilities/')
        self.assertEqual(response.status_code, 401)


    def test_openapi_contract_is_available(self):
        response = self.client.get('/api/v1/platform/openapi/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'openapi: 3.1.0', b''.join(response.streaming_content))
