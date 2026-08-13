from django.test import TestCase

from ai_engine.governance import chunk_evidence, grounded_context, record_evidence_decision
from compliance.models import CompanyControl, Control, Domain, Evidence, Framework
from core.models import Company, User


class EvidenceDecisionGovernanceTests(TestCase):
    def setUp(self):
        framework = Framework.objects.create(code='AI_FW', name='AI Framework')
        domain = Domain.objects.create(framework=framework, code='AI', name='AI Domain')
        control = Control.objects.create(
            framework=framework, domain=domain, control_id='AI-1',
            title='AI control', description='Test control.',
        )
        company = Company.objects.create(
            name='AI Co', cr_number='7300000001', sector='technology', size='small',
            contact_email='ai@example.test', target_nca=True,
        )
        user = User.objects.create_user(email='ai-user@example.test', password='longenough12', company=company)
        company_control = CompanyControl.objects.create(company=company, control=control)
        self.evidence = Evidence.objects.create(
            company_control=company_control, uploaded_by=user, file='evidence/ai.txt',
            original_filename='ai.txt', file_type='txt', file_size=10,
            extracted_text='A' * 1600 + 'B' * 1600,
        )

    def test_chunks_create_cited_context_and_low_confidence_requires_review(self):
        chunks = chunk_evidence(self.evidence, chunk_size=1000)
        self.assertEqual(len(chunks), 4)
        context, cited = grounded_context(self.evidence, max_chars=1300)
        self.assertIn('[chunk:0]', context)
        self.assertEqual(cited, [0, 1])
        decision = record_evidence_decision(self.evidence, {
            'verdict': 'compliant', 'confidence': 0.40, 'model_used': 'test-model',
        })
        self.assertEqual(decision.status, 'review_required')
        self.assertTrue(decision.input_hash)
        self.assertTrue(decision.output_hash)
        self.assertEqual(decision.cited_chunk_indexes, [0, 1, 2, 3])

    def test_invalid_model_output_requires_review(self):
        chunk_evidence(self.evidence)
        decision = record_evidence_decision(self.evidence, {'verdict': 'unknown', 'confidence': 0.9})
        self.assertEqual(decision.status, 'review_required')
