"""R5: every generated PDF states it is NOT an official certification."""
import io

import pdfplumber
from django.test import TestCase

from core.models import Company
from dashboard.reports import gap_analysis_pdf, certificate_pdf


def _text(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as p:
        return '\n'.join(pg.extract_text() or '' for pg in p.pages)


class ReportDisclaimerTests(TestCase):
    def setUp(self):
        self.c = Company.objects.create(name='DiscCo', cr_number='9090909090', sector='technology',
                                        size='small', contact_email='d@x.com')

    def test_gap_pdf_has_non_certification_disclaimer(self):
        text = _text(gap_analysis_pdf(self.c)).lower()
        self.assertIn('not an official', text)
        self.assertIn('does not represent nca', text)

    def test_acknowledgement_pdf_does_not_claim_certification(self):
        from datetime import date
        text = _text(certificate_pdf(self.c, 'NCA-ECC-2-2024', 'REF-1', date.today()))
        low = text.lower()
        self.assertIn('readiness acknowledgement', low)      # neutral wording
        self.assertNotIn('certificate of cybersecurity compliance', low)
        self.assertNotIn('has met the requirements', low)    # no false compliance claim
        self.assertIn('not an official', low)                # disclaimer present
