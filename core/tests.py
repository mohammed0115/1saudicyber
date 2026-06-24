"""
Test suite for CyberTrust KSA (closes the 'no tests' gap, FR Phase-7 QA).
Run: python manage.py test
"""
import io
import os
import tempfile

from django.test import TestCase
from django.urls import reverse

from core.models import User, Company, EmailVerificationToken, AuditLog
from core.forms import CompanyRegistrationForm
from compliance.models import Framework, Domain, Control, CompanyControl


def make_framework_with_controls(code='NCA_ECC', n=3):
    fw, _ = Framework.objects.get_or_create(code=code, defaults={'name': code})
    dom, _ = Domain.objects.get_or_create(framework=fw, name='Governance', defaults={'code': 'GOV'})
    controls = []
    for i in range(1, n + 1):
        controls.append(Control.objects.create(
            framework=fw, domain=dom, control_id=f'{code}-{i}',
            title=f'Control {i}', description='desc', priority='high', evidence_type='policy',
        ))
    return fw, controls


class RegistrationFormTests(TestCase):
    def test_cr_must_be_ten_digits(self):
        form = CompanyRegistrationForm(data={
            'company_name': 'X', 'cr_number': '123', 'sector': 'technology', 'size': 'small',
            'first_name': 'A', 'last_name': 'B', 'email': 'a@b.com',
            'password': 'longenough12', 'target_nca': True})
        self.assertFalse(form.is_valid())
        self.assertIn('cr_number', form.errors)

    def test_password_min_12(self):
        form = CompanyRegistrationForm(data={
            'company_name': 'X', 'cr_number': '1234567890', 'sector': 'technology', 'size': 'small',
            'first_name': 'A', 'last_name': 'B', 'email': 'a@b.com',
            'password': 'short', 'target_nca': True})
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_requires_a_target(self):
        form = CompanyRegistrationForm(data={
            'company_name': 'X', 'cr_number': '1234567890', 'sector': 'technology', 'size': 'small',
            'first_name': 'A', 'last_name': 'B', 'email': 'a@b.com', 'password': 'longenough12'})
        self.assertFalse(form.is_valid())

    def test_valid_form(self):
        form = CompanyRegistrationForm(data={
            'company_name': 'Acme', 'cr_number': '1234567890', 'sector': 'technology', 'size': 'small',
            'first_name': 'A', 'last_name': 'B', 'email': 'good@x.com',
            'password': 'longenough12', 'target_nca': True})
        self.assertTrue(form.is_valid(), form.errors)


class EmailVerificationTests(TestCase):
    def test_verify_email_flow(self):
        user = User.objects.create_user(email='v@x.com', password='longenough12')
        token = EmailVerificationToken.objects.create(user=user, token=EmailVerificationToken.generate())
        resp = self.client.get(reverse('core:verify_email', args=[token.token]))
        self.assertEqual(resp.status_code, 302)
        user.refresh_from_db(); token.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(token.used)


class MFATests(TestCase):
    def test_totp_verify(self):
        import pyotp
        from core.services import mfa_provisioning_uri, verify_totp
        user = User.objects.create_user(email='m@x.com', password='longenough12')
        mfa_provisioning_uri(user)
        self.assertTrue(verify_totp(user, pyotp.TOTP(user.mfa_secret).now()))
        self.assertFalse(verify_totp(user, '000000'))


class ExtractionTests(TestCase):
    def test_txt_extraction(self):
        from ai_engine.services import process_uploaded_file
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('Cybersecurity policy approved by management.'); path = f.name
        out = process_uploaded_file(path, 'txt'); os.unlink(path)
        self.assertIn('policy', out['text'])

    def test_docx_extraction(self):
        from docx import Document
        from ai_engine.services import process_uploaded_file
        doc = Document(); doc.add_paragraph('Incident Response Plan v2')
        path = tempfile.mktemp(suffix='.docx'); doc.save(path)
        out = process_uploaded_file(path, 'docx'); os.unlink(path)
        self.assertIn('Incident Response Plan', out['text'])

    def test_xlsx_extraction(self):
        from openpyxl import Workbook
        from ai_engine.services import process_uploaded_file
        wb = Workbook(); wb.active['A1'] = 'Asset'; wb.active['B1'] = 'Owner'
        path = tempfile.mktemp(suffix='.xlsx'); wb.save(path)
        out = process_uploaded_file(path, 'xlsx'); os.unlink(path)
        self.assertIn('Asset', out['text'])


class MonitoringTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='Co', cr_number='1111111111', sector='technology', size='small',
            contact_email='c@x.com', target_nca=True)
        _, controls = make_framework_with_controls('NCA_ECC', 4)
        for i, c in enumerate(controls):
            CompanyControl.objects.create(
                company=self.company, control=c,
                status='compliant' if i < 2 else 'non_compliant')

    def test_recalculate_score(self):
        from monitoring.services import recalculate_score
        score = recalculate_score(self.company)
        self.assertEqual(score.controls_total, 4)
        self.assertEqual(score.controls_compliant, 2)
        self.assertEqual(score.overall_score, 50.0)

    def test_monthly_report(self):
        from monitoring.services import generate_monthly_report
        report = generate_monthly_report(self.company)
        self.assertEqual(report.report_data['controls_total'], 4)


class ReportingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='RepCo', cr_number='2222222222', sector='technology', size='small',
            contact_email='r@x.com', target_nca=True)
        _, controls = make_framework_with_controls('NCA_ECC', 2)
        for c in controls:
            CompanyControl.objects.create(company=self.company, control=c, status='compliant')

    def test_pdf_bytes(self):
        from dashboard.reports import gap_analysis_pdf
        self.assertTrue(gap_analysis_pdf(self.company).startswith(b'%PDF'))

    def test_excel_bytes(self):
        from dashboard.reports import compliance_excel
        self.assertEqual(compliance_excel(self.company)[:2], b'PK')


class ApiTests(TestCase):
    def test_register_and_jwt_login(self):
        make_framework_with_controls('NCA_ECC', 2)
        payload = {
            'company_name': 'ApiCo', 'cr_number': '3333333333', 'sector': 'technology', 'size': 'small',
            'email': 'api@x.com', 'password': 'longenough12', 'first_name': 'A', 'last_name': 'B',
            'target_nca': True}
        r = self.client.post('/api/v1/register/', data=payload, content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn('access', r.json())
        company = Company.objects.get(cr_number='3333333333')
        self.assertEqual(CompanyControl.objects.filter(company=company).count(), 2)
        auth = {'HTTP_AUTHORIZATION': f"Bearer {r.json()['access']}"}
        rc = self.client.get('/api/v1/controls/', **auth)
        self.assertEqual(rc.status_code, 200)
        self.assertEqual(len(rc.json()), 2)

    def test_controls_requires_auth(self):
        self.assertEqual(self.client.get('/api/v1/controls/').status_code, 401)


class AuditLogTests(TestCase):
    def test_post_is_logged(self):
        User.objects.create_user(email='log@x.com', password='longenough12')
        self.client.post(reverse('core:login'),
                         {'username': 'log@x.com', 'password': 'longenough12'})
        self.assertTrue(AuditLog.objects.filter(path=reverse('core:login')).exists())


class PdplTests(TestCase):
    def test_purge_command_runs(self):
        from django.core.management import call_command
        out = io.StringIO()
        call_command('purge_expired_data', stdout=out)
        self.assertIn('Retention purge complete', out.getvalue())


class RegisterViewTests(TestCase):
    """PATCH #5 (registration validation) + #6 (post-classification control checklist)
    exercised through the real web registration view, end to end."""

    def _payload(self, **over):
        data = {
            'company_name': 'WebCo', 'cr_number': '4444444444', 'sector': 'technology',
            'size': 'small', 'first_name': 'A', 'last_name': 'B', 'email': 'web@x.com',
            'password': 'longenough12', 'target_nca': 'on'}
        data.update(over)
        return data

    def test_invalid_cr_does_not_create_company(self):
        # PATCH #5: bad CR must be rejected by the form, not 500 / silently accepted.
        from unittest import mock
        with mock.patch('core.views.classify_company', return_value={'error': 'skip'}):
            resp = self.client.post(reverse('core:register'), self._payload(cr_number='123'))
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors, no redirect
        self.assertEqual(Company.objects.count(), 0)

    def test_duplicate_cr_rejected(self):
        Company.objects.create(name='Existing', cr_number='4444444444', sector='technology',
                               size='small', contact_email='e@x.com', target_nca=True)
        from unittest import mock
        with mock.patch('core.views.classify_company', return_value={'error': 'skip'}):
            resp = self.client.post(reverse('core:register'), self._payload())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Company.objects.count(), 1)

    def test_successful_registration_builds_checklist(self):
        # PATCH #6: after registration the company's control checklist must be populated.
        fw, controls = make_framework_with_controls('NCA_ECC', 5)
        from unittest import mock
        with mock.patch('core.views.classify_company', return_value={'error': 'skip'}):
            resp = self.client.post(reverse('core:register'), self._payload())
        self.assertEqual(resp.status_code, 302)
        company = Company.objects.get(cr_number='4444444444')
        self.assertEqual(CompanyControl.objects.filter(company=company).count(), 5)


class HealthCheckTests(TestCase):
    """Phase 3L — the Docker/LB liveness probe is public, minimal, and leak-free."""

    def test_healthz_returns_ok_without_login(self):
        resp = self.client.get(reverse('healthz'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok'})

    def test_healthz_exposes_no_sensitive_info(self):
        from django.conf import settings as dj_settings
        body = self.client.get('/healthz/').content.decode()
        self.assertNotIn(dj_settings.SECRET_KEY, body)
        self.assertEqual(body.strip(), '{"status": "ok"}')


# ============================================================
# Phase 4A — Self-service company registration + onboarding
# ============================================================
class Phase4ARegistrationOnboardingTests(TestCase):
    def _payload(self, **over):
        d = {
            'first_name': 'Sara', 'last_name': 'Ali',
            'email': 'sara@co.example', 'phone': '0500000000',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة الاختبار', 'company_name': 'Test Co',
            'cr_number': '1212121212', 'sector': 'technology', 'size': 'small',
            'city': 'Riyadh', 'country': 'SA', 'description': 'وصف',
            'target_nca': 'on',
        }
        d.update(over)
        return d

    # --- Registration / Onboarding ---
    def test_company_self_registration_creates_user(self):
        resp = self.client.post(reverse('core:company_register'), self._payload())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(email='sara@co.example').exists())

    def test_company_self_registration_creates_company(self):
        self.client.post(reverse('core:company_register'), self._payload())
        self.assertTrue(Company.objects.filter(cr_number='1212121212').exists())

    def test_company_linkage_is_correct(self):
        self.client.post(reverse('core:company_register'), self._payload())
        u = User.objects.get(email='sara@co.example')
        self.assertIsNotNone(u.company)
        self.assertEqual(u.company.cr_number, '1212121212')
        self.assertEqual(u.role, 'company_admin')

    def test_registered_user_reaches_onboarding(self):
        resp = self.client.post(reverse('core:company_register'), self._payload())
        self.assertEqual(resp.url, reverse('core:onboarding'))
        follow = self.client.get(reverse('core:onboarding'))
        self.assertEqual(follow.status_code, 200)
        self.assertContains(follow, 'مرحبًا بك في CyberTrust')

    def test_onboarding_completion_redirects_to_journey(self):
        self.client.post(reverse('core:company_register'), self._payload())
        resp = self.client.post(reverse('core:onboarding_complete'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('compliance:dashboard'))
        self.assertTrue(Company.objects.get(cr_number='1212121212').onboarding_completed)

    def test_old_registration_flow_still_works(self):
        from unittest import mock
        with mock.patch('core.views.classify_company', return_value={'error': 'skip'}):
            resp = self.client.post(reverse('core:register'), {
                'company_name': 'Legacy Co', 'cr_number': '9090909090', 'sector': 'technology',
                'size': 'small', 'first_name': 'A', 'last_name': 'B', 'email': 'legacy@x.com',
                'password': 'longenough12', 'target_nca': 'on'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='9090909090').exists())

    def test_registration_rejects_password_mismatch(self):
        resp = self.client.post(reverse('core:company_register'),
                                self._payload(password_confirm='different12345'))
        self.assertEqual(resp.status_code, 200)  # re-render with error
        self.assertFalse(Company.objects.filter(cr_number='1212121212').exists())

    def test_registration_requires_a_goal(self):
        resp = self.client.post(reverse('core:company_register'),
                                self._payload(target_nca='', target_aramco='', target_sabic=''))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email='sara@co.example').exists())

    # --- Tenant / Security ---
    def test_protected_onboarding_requires_login(self):
        resp = self.client.get(reverse('core:onboarding'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_onboarding_complete_requires_login(self):
        resp = self.client.post(reverse('core:onboarding_complete'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_onboarding_shows_only_own_company(self):
        self.client.post(reverse('core:company_register'), self._payload())
        Company.objects.create(name='OtherCorp ZZZ', cr_number='7777777777',
                               sector='technology', size='small', contact_email='o@x.com')
        resp = self.client.get(reverse('core:onboarding'))
        self.assertContains(resp, 'شركة الاختبار')
        self.assertNotContains(resp, 'OtherCorp ZZZ')

    def test_no_cross_company_leakage_on_dashboard(self):
        self.client.post(reverse('core:company_register'), self._payload())
        Company.objects.create(name='OtherCorp ZZZ', cr_number='7777777777',
                               sector='technology', size='small', contact_email='o@x.com')
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'OtherCorp ZZZ')

    # --- UX / Flow rendering ---
    def test_get_started_page_renders_with_company_option(self):
        resp = self.client.get(reverse('core:get_started'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('core:company_register'))
        self.assertContains(resp, 'شركة / جهة طالبة امتثال')

    def test_registration_page_renders(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'سجّل شركتك في CyberTrust')

    def test_onboarding_page_renders(self):
        self.client.post(reverse('core:company_register'), self._payload())
        resp = self.client.get(reverse('core:onboarding'))
        self.assertContains(resp, 'مراحل رحلتك')

    def test_loading_overlay_present_and_render_intact(self):
        # The calm loading overlay markup is present and does not break the page.
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'ct-busy-overlay')
        self.assertContains(resp, 'data-busy')

    def test_auditor_placeholder_renders(self):
        resp = self.client.get(reverse('core:auditor_register'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'مسار المدقّق')


class Phase4ABackwardCompatTests(TestCase):
    """The new fields/flow must not break the existing compliance journey."""
    def setUp(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())

    def _registered_client(self):
        self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bc4a@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC Co', 'cr_number': '1313131313',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on'})

    def test_journey_pages_still_work_for_registered_company(self):
        self._registered_client()
        for name in ['compliance:intake', 'compliance:applicability_review',
                     'compliance:control_plan', 'compliance:evidence_checklist',
                     'compliance:auditor_review_queue', 'compliance:reports_index']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_evidence_upload_v2_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.models import EvidenceSubmission
        c, item, sub = _company_with_submission()
        self.assertTrue(EvidenceSubmission.objects.filter(id=sub.id).exists())

    def test_evidence_analysis_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        analyze_evidence_submission(sub, apply=True)
        self.assertTrue(EvidenceAnalysisResult.objects.filter(evidence_submission=sub).exists())

    def test_auditor_assessment_and_reports_still_work(self):
        from compliance.tests import _company_with_assessments
        from compliance.control_assessment import update_assessment_from_auditor_input
        from compliance.reporting import build_executive_summary
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        u = User.objects.create_user(email='aud4a@x.com', password='longenough12',
                                     company=c, is_staff=True)
        update_assessment_from_auditor_input(a, {'status': 'compliant'}, u)
        a.refresh_from_db()
        self.assertEqual(a.status, 'compliant')
        self.assertEqual(build_executive_summary(c)['counts']['compliant'], 1)
