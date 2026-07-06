"""Evidence pipeline reliability: it must NEVER leave a row stuck at 'processing'.

Covers: a crash mid-analysis lands the row on a terminal status with ai_verdict='error';
empty OCR (e.g. Tesseract not installed) is 'insufficient_evidence', not an error, and not
stuck; and the process_pending_evidence command drains stuck rows.
"""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from compliance.tests import _company_with_control
from compliance.models import CompanyControl, Evidence
from compliance.services import process_evidence_pipeline


def _evidence(company, control, status='processing'):
    cc = CompanyControl.objects.get_or_create(company=company, control=control)[0]
    return Evidence.objects.create(
        company_control=cc, uploaded_by=None,
        file=SimpleUploadedFile('p.txt', b'policy text'), original_filename='p.txt',
        file_type='txt', file_size=11, status=status)


class PipelineReliabilityTests(TestCase):
    def test_crash_mid_analysis_lands_terminal_error_not_processing(self):
        c, control = _company_with_control()
        ev = _evidence(c, control)
        with mock.patch('compliance.services.process_uploaded_file',
                        return_value={'text': 'some text', 'confidence': 1.0, 'language': 'en'}), \
             mock.patch('compliance.services.analyze_evidence', side_effect=RuntimeError('boom')):
            result = process_evidence_pipeline(ev.id)
        ev.refresh_from_db()
        self.assertNotEqual(ev.status, 'processing')        # never stuck
        self.assertNotEqual(ev.status, 'ai_analyzing')
        self.assertEqual(ev.ai_verdict, 'error')            # visible failure state
        self.assertIn('error', result)

    def test_empty_ocr_is_insufficient_not_error_not_stuck(self):
        c, control = _company_with_control()
        ev = _evidence(c, control)
        with mock.patch('compliance.services.process_uploaded_file',
                        return_value={'text': '', 'confidence': 0.0, 'language': ''}):
            result = process_evidence_pipeline(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.status, 'reviewed')             # terminal
        self.assertNotEqual(ev.ai_verdict, 'error')
        self.assertEqual(result['verdict'], 'insufficient_evidence')

    def test_missing_evidence_id_is_safe(self):
        self.assertEqual(process_evidence_pipeline(999999), {'error': 'evidence not found'})


class ProcessPendingEvidenceCommandTests(TestCase):
    def test_command_drains_stuck_rows(self):
        c, control = _company_with_control()
        ev = _evidence(c, control, status='processing')
        out = StringIO()
        with mock.patch('compliance.services.process_uploaded_file',
                        return_value={'text': '', 'confidence': 0.0, 'language': ''}):
            call_command('process_pending_evidence', stdout=out)
        ev.refresh_from_db()
        self.assertNotEqual(ev.status, 'processing')
        self.assertIn('None left as processing', out.getvalue())
