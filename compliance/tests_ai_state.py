"""Control-detail must show an honest state for un-analyzed Evidence.

When automated analysis is NOT configured (no OPENAI_API_KEY), evidence with no
ai_verdict must read "Pending human review", not a fake "Processing"/AI spinner.
When it IS configured, "AI processing" is allowed. UI-only; no backend behaviour change.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from compliance.tests import _company_with_control, _journey_user, _SUF
from compliance.models import CompanyControl, Evidence


class ControlDetailAiStateTests(TestCase):
    def _setup(self):
        c, control = _company_with_control()
        cc = CompanyControl.objects.get_or_create(company=c, control=control)[0]
        Evidence.objects.create(company_control=cc, uploaded_by=None,
                                file=_SUF('p.pdf', b'%PDF-1.4'), original_filename='p.pdf',
                                file_type='pdf', file_size=8, status='uploaded', ai_verdict='')
        self.client.force_login(_journey_user(c, email='aistate@x.com'))
        return control

    @override_settings(OPENAI_API_KEY='')
    def test_no_key_shows_pending_human_review_not_processing(self):
        control = self._setup()
        body = self.client.get(reverse('compliance:control_detail', args=[control.id])).content.decode()
        self.assertIn('بانتظار مراجعة بشرية', body)     # honest state (Arabic label)
        self.assertNotIn('جارٍ التحليل', body)

    @override_settings(OPENAI_API_KEY='sk-test-key')
    def test_key_present_allows_ai_processing_label(self):
        control = self._setup()
        body = self.client.get(reverse('compliance:control_detail', args=[control.id])).content.decode()
        self.assertIn('جارٍ التحليل', body)             # AI processing (Arabic label)
        self.assertNotIn('بانتظار مراجعة بشرية', body)
