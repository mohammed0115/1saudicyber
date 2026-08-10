"""R1: the advisory-AI page shows an HONEST, specific reason when analysis is unavailable."""
from django.test import TestCase, override_settings
from django.urls import reverse

from compliance.tests import _company_with_submission, _journey_user
from compliance.models import EvidenceTextExtraction


def _with_extraction(sub):
    """Give the submission a successful text extraction so the AI-service gate is the active one."""
    EvidenceTextExtraction.objects.update_or_create(
        submission=sub, defaults=dict(status='extracted',
                                      extracted_text='approved cybersecurity policy text',
                                      char_count=34))
    return sub


class AiAdvisoryVisibilityTests(TestCase):
    @override_settings(OPENAI_API_KEY='sk-test-key', AI_DATA_RESIDENCY_MODE='disabled')
    def test_preview_shows_residency_reason_not_generic(self):
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        _with_extraction(sub)
        self.client.force_login(_journey_user(c, email='aiv@x.com'))
        body = self.client.get(
            reverse('compliance:evidence_ai_analysis', args=[sub.id])).content.decode()
        self.assertIn('سيادة البيانات', body)          # honest, specific reason
        self.assertIn('AI_DATA_RESIDENCY_MODE=external', body)  # how to enable

    @override_settings(OPENAI_API_KEY='', AI_DATA_RESIDENCY_MODE='external')
    def test_preview_shows_no_key_reason(self):
        c, item, sub = _company_with_submission(fv_code='NCA-ECC-2-2024')
        _with_extraction(sub)
        self.client.force_login(_journey_user(c, email='aiv2@x.com'))
        body = self.client.get(
            reverse('compliance:evidence_ai_analysis', args=[sub.id])).content.decode()
        self.assertIn('مفتاح', body)
