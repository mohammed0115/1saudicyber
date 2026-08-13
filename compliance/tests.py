from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from compliance.file_validation import validate_evidence_upload
from compliance.models import CompanyControl, Control, Domain, Evidence, Framework
from compliance.services import process_evidence_pipeline
from core.models import Company, User


class EvidencePipelineTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Evidence Co', cr_number='9090909090', sector='technology', size='small',
            contact_email='evidence@example.com', target_nca=True,
        )
        self.user = User.objects.create_user(
            email='evidence.user@example.com', password='longenough12', company=self.company,
        )
        self.framework = Framework.objects.create(code='NCA_ECC', name='NCA')
        self.domain = Domain.objects.create(framework=self.framework, code='GOV', name='Governance')
        self.control = Control.objects.create(
            framework=self.framework, domain=self.domain, control_id='NCA-TEST-1',
            title='Policy', description='A current approved security policy is required.',
        )
        self.company_control = CompanyControl.objects.create(company=self.company, control=self.control)

    def make_evidence(self, content=b'policy content'):
        return Evidence.objects.create(
            company_control=self.company_control,
            uploaded_by=self.user,
            file=SimpleUploadedFile('evidence.txt', content, content_type='text/plain'),
            original_filename='evidence.txt', file_type='txt', file_size=len(content), status='processing',
        )

    def test_signature_mismatch_is_rejected(self):
        upload = SimpleUploadedFile('policy.pdf', b'not a PDF', content_type='application/pdf')
        with self.assertRaises(ValidationError):
            validate_evidence_upload(upload)

    @patch('compliance.services.process_uploaded_file')
    def test_unreadable_evidence_requires_manual_review_without_control_update(self, extract):
        extract.return_value = {'text': '', 'confidence': 0.0, 'language': '', 'error': 'OCR failed'}
        evidence = self.make_evidence()

        result = process_evidence_pipeline(evidence.id)

        evidence.refresh_from_db()
        self.company_control.refresh_from_db()
        self.assertEqual(result['status'], 'needs_manual_review')
        self.assertEqual(evidence.status, 'needs_manual_review')
        self.assertEqual(self.company_control.status, 'not_started')

    @patch('compliance.services.analyze_evidence')
    @patch('compliance.services.process_uploaded_file')
    def test_valid_analysis_marks_control_reviewed(self, extract, analyze):
        extract.return_value = {'text': 'Approved policy version 1.', 'confidence': 0.95, 'language': 'en'}
        analyze.return_value = {
            'verdict': 'compliant', 'confidence': 0.87,
            'reasoning_en': 'The policy is approved.', 'reasoning_ar': 'السياسة معتمدة.',
            'key_findings_en': ['approval'], 'key_findings_ar': ['اعتماد'],
            'recommendations_en': [], 'recommendations_ar': [],
            'evidence_quality': 'high', 'missing_elements': [], 'risk_if_unresolved': '',
        }
        evidence = self.make_evidence()

        result = process_evidence_pipeline(evidence.id)

        evidence.refresh_from_db()
        self.company_control.refresh_from_db()
        self.assertEqual(result['status'], 'reviewed')
        self.assertEqual(evidence.status, 'reviewed')
        self.assertEqual(self.company_control.status, 'ai_reviewed')
        self.assertEqual(self.company_control.ai_confidence, 0.87)

    @patch('compliance.services.analyze_evidence')
    @patch('compliance.services.process_uploaded_file')
    def test_invalid_ai_output_fails_without_control_update(self, extract, analyze):
        extract.return_value = {'text': 'Some policy content', 'confidence': 1.0, 'language': 'en'}
        analyze.return_value = {'verdict': 'unsupported'}
        evidence = self.make_evidence()

        result = process_evidence_pipeline(evidence.id)

        evidence.refresh_from_db()
        self.company_control.refresh_from_db()
        self.assertIn('Invalid AI evidence response', result['error'])
        self.assertEqual(evidence.status, 'failed')
        self.assertEqual(self.company_control.status, 'not_started')
