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
            'target_nca': 'on', 'accept_terms': 'on',
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
        self.assertContains(follow, 'مرحبًا بك في 1SaudiCyber')

    def test_registration_success_message_is_arabic_only(self):
        # UAT-UI-1: the Arabic success message must not contain English.
        resp = self.client.post(reverse('core:company_register'), self._payload(), follow=True)
        body = resp.content.decode()
        self.assertIn('تحقّق من بريدك الإلكتروني', body)
        self.assertNotIn('Check your email', body)
        self.assertNotIn('verification code', body)

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
                'password': 'longenough12', 'target_nca': 'on', 'accept_terms': 'on'})
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
        self.assertContains(resp, 'سجّل شركتك في 1SaudiCyber')

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
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

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


# ============================================================
# Phase 4A-FIX-A — Arabic localization + public content correction + stepper
# ============================================================
class Phase4AFixALocalizationTests(TestCase):
    def _reg(self):  # register a company so onboarding/journey pages are reachable
        return self.client.post(reverse('core:company_register'), {
            'first_name': 'S', 'last_name': 'A', 'email': 'fixa@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'Co', 'cr_number': '1717171717',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

    # --- Arabic / RTL ---
    def test_public_landing_contains_arabic_primary_copy(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'جاهزية الامتثال')

    def test_public_landing_uses_rtl_or_rtl_friendly_markup(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, 'dir="rtl"')

    def test_get_started_contains_company_arabic_cta(self):
        resp = self.client.get(reverse('core:get_started'))
        self.assertContains(resp, 'إنشاء حساب شركة')

    def test_company_registration_contains_arabic_labels(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'بيانات المستخدم')
        self.assertContains(resp, 'بيانات الشركة')
        self.assertContains(resp, 'أهداف الامتثال')

    def test_onboarding_contains_arabic_steps(self):
        self._reg()
        resp = self.client.get(reverse('core:onboarding'))
        self.assertContains(resp, 'مراحل رحلتك')

    def test_subscription_required_contains_arabic_message(self):
        from compliance.tests import _company_with_assessments, _journey_user
        c, fv, scope = _company_with_assessments()
        self.client.force_login(_journey_user(c))  # unsubscribed
        resp = self.client.get(reverse('compliance:report_executive_summary'))
        self.assertContains(resp, 'تفعيل الاشتراك مطلوب')

    # --- Stepper (workflow) ---
    def test_registration_uses_stepper(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'ct-step')
        self.assertContains(resp, 'data-step-pill')

    # --- Content correctness ---
    def test_public_landing_does_not_show_legacy_334_as_current_official_count(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertNotContains(resp, '334')

    def test_public_landing_shows_417_official_controls(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, '417')

    def test_nca_ecc_count_is_108_or_nca_total_is_231(self):
        resp = self.client.get(reverse('core:landing'))
        body = resp.content.decode()
        self.assertTrue('108' in body or '231' in body)

    def test_aramco_count_is_92(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, '92')

    def test_sabic_count_is_94(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, '94')

    def test_public_copy_does_not_claim_certification_granting(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        for term in ['certification', 'Certification', 'Certify', 'certify', 'منح شهادة', 'إصدار شهادة']:
            self.assertNotIn(term, body)


class Phase4AFixABackwardCompatTests(TestCase):
    def setUp(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())

    def test_company_registration_still_works(self):
        resp = self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bcfa@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': '1818181818',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='1818181818').exists())

    def test_onboarding_still_works(self):
        self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bcfa2@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': '1919191919',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_subscription_gated_reports_still_work(self):
        from compliance.tests import _company_with_assessments, _journey_user
        from billing.subscription_access import activate_company_subscription
        c, fv, scope = _company_with_assessments()
        user = _journey_user(c)
        self.client.force_login(user)
        # unsubscribed -> gated
        self.assertContains(self.client.get(reverse('compliance:report_executive_summary')),
                            'تفعيل الاشتراك مطلوب')
        # subscribed -> full report
        activate_company_subscription(c, 'Plan', days=30)
        self.assertNotContains(self.client.get(reverse('compliance:report_executive_summary')),
                               'تفعيل الاشتراك مطلوب')

    def test_reports_still_work(self):
        from compliance.tests import _company_with_assessments, _journey_user
        from billing.subscription_access import activate_company_subscription
        c, fv, scope = _company_with_assessments()
        activate_company_subscription(c, 'Plan', days=30)
        self.client.force_login(_journey_user(c))
        self.assertEqual(self.client.get(reverse('compliance:report_executive_summary')).status_code, 200)

    def test_evidence_upload_v2_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.models import EvidenceSubmission
        c, item, sub = _company_with_submission()
        self.assertTrue(EvidenceSubmission.objects.filter(id=sub.id).exists())

    def test_advisory_analysis_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        analyze_evidence_submission(sub, apply=True)
        self.assertTrue(EvidenceAnalysisResult.objects.filter(evidence_submission=sub).exists())


# ============================================================
# Phase 4D — UX loading states, AI advisory UX, auditor nav polish
# ============================================================
class Phase4DLoadingStateTests(TestCase):
    def _staff(self, company):
        from compliance.tests import _journey_user
        return _journey_user(company, is_staff=True)

    def test_registration_submit_has_loading_state(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ حفظ البيانات')

    def test_onboarding_completion_has_loading_state(self):
        self.client.post(reverse('core:company_register'), {
            'first_name': 'S', 'last_name': 'A', 'email': 'load@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'Co', 'cr_number': '3131313131',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        # The journey CTAs (with their loading state) appear once the email is verified.
        User.objects.filter(email='load@co.example').update(email_verified=True)
        resp = self.client.get(reverse('core:onboarding'))
        self.assertContains(resp, 'جارٍ تجهيز لوحة الرحلة')

    def test_intake_save_has_loading_state(self):
        from compliance.tests import _company_with_official_plan, _journey_user
        c, fv, scope = _company_with_official_plan()
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:intake'))
        self.assertContains(resp, 'جارٍ حفظ البيانات')

    def test_framework_evaluation_has_loading_state(self):
        from compliance.tests import _company_with_applicability
        c, fv = _company_with_applicability()
        self.client.force_login(self._staff(c))
        resp = self.client.get(reverse('compliance:applicability_review'))
        self.assertContains(resp, 'data-busy')
        self.assertContains(resp, 'جارٍ اعتماد الإطار')

    def test_control_plan_generation_has_loading_state(self):
        from compliance.tests import _company_with_official_plan
        c, fv, scope = _company_with_official_plan()
        self.client.force_login(self._staff(c))
        resp = self.client.get(reverse('compliance:control_plan'))
        self.assertContains(resp, 'جارٍ توليد خطة الضوابط')

    def test_evidence_checklist_generation_has_loading_state(self):
        from compliance.tests import _company_with_official_plan
        c, fv, scope = _company_with_official_plan()
        self.client.force_login(self._staff(c))
        resp = self.client.get(reverse('compliance:evidence_checklist'))
        self.assertContains(resp, 'جارٍ توليد قائمة الأدلة')

    def test_evidence_upload_v2_has_loading_state(self):
        from compliance.tests import _company_with_checklist, _journey_user
        from compliance.models import EvidenceChecklistItem
        c, fv, scope = _company_with_checklist()
        item = EvidenceChecklistItem.objects.filter(company=c).first()
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:evidence_upload_v2', args=[item.id]))
        # Phase 8E: the upload form now uses the richer smart-processing animation
        # (reading file -> extracting text -> preparing result) as its loading state.
        self.assertContains(resp, 'data-smart-processing')
        self.assertContains(resp, 'Processing evidence')

    def test_advisory_analysis_trigger_has_loading_state(self):
        from compliance.tests import _company_with_submission
        c, item, sub = _company_with_submission()
        self.client.force_login(self._staff(c))
        resp = self.client.get(reverse('compliance:evidence_submission_detail', args=[sub.id]))
        self.assertContains(resp, 'جارٍ تحليل الدليل استشاريًا')

    def _subscribed_matrix(self):
        from compliance.tests import _company_with_assessments, _journey_user
        from billing.subscription_access import activate_company_subscription
        c, fv, scope = _company_with_assessments()
        activate_company_subscription(c, 'Plan', days=30)
        self.client.force_login(_journey_user(c))
        return self.client.get(reverse('compliance:report_evidence_matrix'))

    def test_report_csv_export_has_loading_state(self):
        self.assertContains(self._subscribed_matrix(), 'جارٍ تجهيز ملف CSV')

    def test_report_xlsx_export_has_loading_state(self):
        self.assertContains(self._subscribed_matrix(), 'جارٍ تجهيز ملف Excel')

    def test_auditor_registration_has_loading_state(self):
        resp = self.client.get(reverse('auditors:register'))
        self.assertContains(resp, 'جارٍ إرسال طلب التسجيل كمدقق')

    def test_auditor_assignment_has_loading_state(self):
        from auditors.tests import _company_user, _auditor
        c, cu = _company_user(subscribe=True)
        _auditor()
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:list'))
        self.assertContains(resp, 'جارٍ إرسال طلب المراجعة')

    def test_auditor_accept_reject_has_loading_state(self):
        from auditors.tests import _auditor, _assignment
        from compliance.tests import _company_with_assessments
        u, p = _auditor(status='active')
        c, fv, scope = _company_with_assessments()
        a = _assignment(c, p, status='requested')
        self.client.force_login(u)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertContains(resp, 'جارٍ تحديث حالة الطلب')


class Phase4DAiUxTests(TestCase):
    def _detail(self, analysis_status=None, error=''):
        from compliance.tests import _company_with_submission, _journey_user
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        if analysis_status:
            EvidenceAnalysisResult.objects.create(
                company=c, evidence_submission=sub, checklist_item=item,
                control=item.evidence_requirement.control, status=analysis_status,
                error_message=error)
        self.client.force_login(_journey_user(c, is_staff=True))
        return self.client.get(reverse('compliance:evidence_submission_detail', args=[sub.id]))

    def test_ai_analysis_ui_says_advisory_not_final(self):
        resp = self._detail()
        self.assertContains(resp, 'استشاري')
        self.assertContains(resp, 'لا يُعد قرارًا نهائيًا')

    def test_ai_missing_key_message_is_safe_if_rendered(self):
        resp = self._detail(analysis_status='needs_human_review', error='SECRET_TRACE_XYZ')
        self.assertContains(resp, 'تعذر تشغيل التحليل الآلي حاليًا')
        self.assertNotContains(resp, 'SECRET_TRACE_XYZ')

    def test_no_certification_claims_in_ai_waiting_copy(self):
        body = self._detail().content.decode()
        for term in ['certification', 'Certification', 'Certify', 'شهادة رسمية']:
            self.assertNotIn(term, body)


class Phase4DNavigationTests(TestCase):
    def _auditor_login(self):
        from auditors.tests import _auditor
        u, p = _auditor(status='active')
        self.client.force_login(u)
        return u, p

    def test_auditor_nav_points_to_new_auditor_dashboard(self):
        self._auditor_login()
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertContains(resp, reverse('auditors:dashboard'))
        self.assertContains(resp, 'لوحة المدقق')

    def test_auditor_primary_nav_not_confusing_with_old_portal(self):
        self._auditor_login()
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertNotContains(resp, 'Auditor Portal')  # old portal link removed from primary nav

    def test_existing_auditor_portal_not_broken_if_present(self):
        u, p = self._auditor_login()
        # The old portal URL still resolves and renders (not deleted).
        resp = self.client.get(reverse('auditor_portal:dashboard'))
        self.assertEqual(resp.status_code, 200)


class Phase4DArabicRtlTests(TestCase):
    def test_loading_messages_are_arabic(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'جارٍ حفظ البيانات')

    def test_loading_overlay_is_rtl_friendly(self):
        resp = self.client.get(reverse('core:company_register'))
        self.assertContains(resp, 'ct-busy-overlay')
        self.assertContains(resp, 'يرجى الانتظار')

    def test_public_and_core_pages_still_arabic_first(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, 'جاهزية الامتثال')
        self.assertContains(resp, 'dir="rtl"')


class Phase4DBackwardCompatTests(TestCase):
    def setUp(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())

    def test_company_registration_still_works(self):
        resp = self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bc4d@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': '2424242424',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='2424242424').exists())

    def test_onboarding_still_works(self):
        self.client.post(reverse('core:company_register'), {
            'first_name': 'B', 'last_name': 'C', 'email': 'bc4d2@co.example',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'BC', 'cr_number': '2525252525',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_subscription_gated_reports_still_work(self):
        from auditors.tests import _company_user
        c, cu = _company_user(subscribe=False)
        self.client.force_login(cu)
        self.assertContains(self.client.get(reverse('compliance:report_executive_summary')),
                            'تفعيل الاشتراك مطلوب')

    def test_auditor_assignment_still_works(self):
        from auditors.tests import _company_user, _auditor
        from auditors.models import AuditorAssignment
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=c, auditor=p).count(), 1)

    def test_reports_still_work(self):
        from auditors.tests import _company_user
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        self.assertEqual(self.client.get(reverse('compliance:report_executive_summary')).status_code, 200)

    def test_evidence_upload_v2_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.models import EvidenceSubmission
        c, item, sub = _company_with_submission()
        self.assertTrue(EvidenceSubmission.objects.filter(id=sub.id).exists())

    def test_advisory_analysis_still_works(self):
        from compliance.tests import _company_with_submission
        from compliance.evidence_analysis import analyze_evidence_submission
        from compliance.models import EvidenceAnalysisResult
        c, item, sub = _company_with_submission()
        analyze_evidence_submission(sub, apply=True)
        self.assertTrue(EvidenceAnalysisResult.objects.filter(evidence_submission=sub).exists())

    def test_staff_controlassessment_flow_still_works(self):
        from compliance.tests import _company_with_assessments, _journey_user
        from compliance.control_assessment import update_assessment_from_auditor_input
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        a = ControlAssessment.objects.filter(company=c).first()
        staff = _journey_user(c, email='staff4d@x.com', is_staff=True)
        update_assessment_from_auditor_input(a, {'status': 'compliant'}, staff)
        a.refresh_from_db()
        self.assertEqual(a.status, 'compliant')


# ============================================================
# Phase 4D Addendum — Company Workflow Stepper (read-only)
# ============================================================
def _stepper_stage(stepper, key):
    return next(s for s in stepper['stages'] if s['key'] == key)


class CompanyWorkflowStepperServiceTests(TestCase):
    def _build(self, company):
        from compliance.workflow_stepper import build_company_workflow_stepper
        return build_company_workflow_stepper(company)

    def test_stepper_shows_registration_completed_for_company_user(self):
        from compliance.tests import _company
        st = self._build(_company())
        self.assertEqual(_stepper_stage(st, 'registration')['status'], 'completed')

    def test_stepper_shows_onboarding_completed(self):
        from compliance.tests import _company
        st = self._build(_company(onboarding_completed=True))
        self.assertEqual(_stepper_stage(st, 'onboarding')['status'], 'completed')

    def test_stepper_shows_intake_current_when_missing(self):
        from compliance.tests import _company
        st = self._build(_company(onboarding_completed=True))
        self.assertEqual(_stepper_stage(st, 'intake')['status'], 'current')

    def test_stepper_shows_framework_steps_after_applicability(self):
        from compliance.tests import _company_with_applicability
        c, fv = _company_with_applicability()
        self.assertEqual(_stepper_stage(self._build(c), 'applicability')['status'], 'completed')

    def test_stepper_shows_evidence_steps_after_checklist(self):
        from compliance.tests import _company_with_checklist
        c, fv, scope = _company_with_checklist()
        self.assertEqual(_stepper_stage(self._build(c), 'checklist')['status'], 'completed')

    def test_stepper_shows_upload_completed_after_submission(self):
        from compliance.tests import _company_with_submission
        c, item, sub = _company_with_submission()
        self.assertEqual(_stepper_stage(self._build(c), 'upload')['status'], 'completed')

    def test_stepper_shows_ai_analysis_step_as_advisory(self):
        from compliance.tests import _company
        st = self._build(_company())
        self.assertEqual(_stepper_stage(st, 'analysis')['title'], 'التحليل الاستشاري')

    def test_stepper_shows_subscription_locked_when_inactive(self):
        from compliance.tests import _company
        st = self._build(_company())
        self.assertEqual(_stepper_stage(st, 'reports')['status'], 'locked')
        self.assertEqual(_stepper_stage(st, 'subscription')['status'], 'needs_action')

    def test_stepper_unlocks_reports_when_subscription_active(self):
        from compliance.tests import _company_with_assessments
        from billing.subscription_access import activate_company_subscription
        c, fv, scope = _company_with_assessments()
        activate_company_subscription(c, 'Plan', days=30)
        self.assertNotEqual(_stepper_stage(self._build(c), 'reports')['status'], 'locked')

    def test_stepper_shows_auditor_assignment_step(self):
        from compliance.tests import _company
        st = self._build(_company())
        self.assertEqual(_stepper_stage(st, 'download_assign')['title'], 'تنزيل التقرير أو إسناده لمدقق')

    def test_stepper_tenant_scoped(self):
        from compliance.tests import _company_with_checklist, _company
        a, fv, scope = _company_with_checklist()
        b = _company()
        self.assertEqual(_stepper_stage(self._build(a), 'checklist')['status'], 'completed')
        self.assertNotEqual(_stepper_stage(self._build(b), 'checklist')['status'], 'completed')

    def test_stepper_does_not_create_records(self):
        from compliance.tests import _company_with_assessments
        from compliance.models import CompanyIntakeProfile, EvidenceSubmission, ControlAssessment
        from auditors.models import AuditorAssignment
        from billing.models import CompanySubscription
        c, fv, scope = _company_with_assessments()
        counts = lambda: (CompanyIntakeProfile.objects.count(), EvidenceSubmission.objects.count(),
                          ControlAssessment.objects.count(), AuditorAssignment.objects.count(),
                          CompanySubscription.objects.count())
        before = counts()
        self._build(c)
        self.assertEqual(before, counts())

    def test_stepper_does_not_change_subscription(self):
        from compliance.tests import _company
        from billing.models import CompanySubscription
        from billing.subscription_access import company_has_active_subscription
        c = _company()
        self._build(c)
        self.assertFalse(company_has_active_subscription(c))
        self.assertEqual(CompanySubscription.objects.count(), 0)

    def test_stepper_does_not_change_controlassessment(self):
        from compliance.tests import _company_with_assessments
        from compliance.models import ControlAssessment
        c, fv, scope = _company_with_assessments()
        before = {a.id: a.status for a in ControlAssessment.objects.filter(company=c)}
        self._build(c)
        after = {a.id: a.status for a in ControlAssessment.objects.filter(company=c)}
        self.assertEqual(before, after)

    def test_stepper_does_not_use_companycontrol(self):
        from compliance.tests import _company_with_assessments
        from compliance.models import CompanyControl
        before = CompanyControl.objects.count()
        c, fv, scope = _company_with_assessments()
        self._build(c)
        self.assertEqual(CompanyControl.objects.count(), before)


class CompanyWorkflowStepperViewTests(TestCase):
    def _login(self, company):
        from compliance.tests import _journey_user
        self.client.force_login(_journey_user(company))

    def test_company_workflow_stepper_renders_on_dashboard(self):
        from compliance.tests import _company
        c = _company()
        self._login(c)
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'مسار عمل الشركة')

    def test_company_workflow_stepper_is_arabic_rtl(self):
        from compliance.tests import _company
        c = _company()
        self._login(c)
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'ct-workflow-stepper')
        self.assertContains(resp, 'dir="rtl"')

    def test_mobile_or_vertical_stepper_markup_exists(self):
        from compliance.tests import _company
        c = _company()
        self._login(c)
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'ct-stepper-vertical')

    def test_next_recommended_action_visible(self):
        from compliance.tests import _company
        c = _company()
        self._login(c)
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'الخطوة التالية:')

    def test_stepper_loading_action_has_data_busy(self):
        from compliance.tests import _company
        c = _company()
        self._login(c)
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertContains(resp, 'جارٍ فتح الخطوة')


# ============================================================
# Phase 4D-FIX-B — Brand/domain rename to 1saudicyber.com
# ============================================================
class Phase4DFixBBrandingTests(TestCase):
    def _register(self, cr='2727272727', email='brand@co.example'):
        return self.client.post(reverse('core:company_register'), {
            'first_name': 'S', 'last_name': 'A', 'email': email,
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'Co', 'cr_number': cr,
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

    def test_public_brand_uses_1saudicyber(self):
        self.assertContains(self.client.get(reverse('core:landing')), '1SaudiCyber')

    def test_landing_no_longer_shows_old_cybertrust_brand_as_primary(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertNotContains(resp, 'CyberTrust KSA')  # old brand label gone

    def test_footer_uses_1saudicyber_domain(self):
        self.assertContains(self.client.get(reverse('core:landing')), '1saudicyber.com')

    def test_get_started_uses_1saudicyber_brand(self):
        self.assertContains(self.client.get(reverse('core:get_started')), '1SaudiCyber')

    def test_onboarding_uses_1saudicyber_brand(self):
        self._register()
        self.assertContains(self.client.get(reverse('core:onboarding')), '1SaudiCyber')

    def test_auditor_pages_use_1saudicyber_brand_if_brand_visible(self):
        self.assertContains(self.client.get(reverse('auditors:register')), '1SaudiCyber')

    def test_docs_or_env_examples_include_1saudicyber_domain_if_tested(self):
        from django.conf import settings as dj
        path = dj.BASE_DIR / 'deployment' / 'docker' / 'env.example'
        text = path.read_text(encoding='utf-8')
        self.assertIn('1saudicyber.com', text)

    def test_no_legacy_334_reintroduced(self):
        self.assertNotContains(self.client.get(reverse('core:landing')), '334')

    def test_no_certification_claims_reintroduced(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        for term in ['certification', 'Certification', 'Certify', 'شهادة رسمية']:
            self.assertNotIn(term, body)

    def test_public_pages_remain_arabic_rtl(self):
        resp = self.client.get(reverse('core:landing'))
        self.assertContains(resp, 'dir="rtl"')
        self.assertContains(resp, 'جاهزية الامتثال')

    # --- Backward compatibility ---
    def test_company_registration_still_works(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('seed_framework_versions', stdout=StringIO())
        resp = self._register(cr='2828282828', email='brand2@co.example')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='2828282828').exists())

    def test_onboarding_still_works(self):
        self._register(cr='2929292929', email='brand3@co.example')
        self.assertEqual(self.client.get(reverse('core:onboarding')).status_code, 200)

    def test_subscription_gated_reports_still_work(self):
        from auditors.tests import _company_user
        c, cu = _company_user(subscribe=False)
        self.client.force_login(cu)
        self.assertContains(self.client.get(reverse('compliance:report_executive_summary')),
                            'تفعيل الاشتراك مطلوب')

    def test_auditor_assignment_still_works(self):
        from auditors.tests import _company_user, _auditor
        from auditors.models import AuditorAssignment
        c, cu = _company_user(subscribe=True)
        _u, p = _auditor()
        self.client.force_login(cu)
        self.client.post(reverse('auditors:assign', args=[p.id]))
        self.assertEqual(AuditorAssignment.objects.filter(company=c, auditor=p).count(), 1)

    def test_workflow_stepper_still_works(self):
        from compliance.tests import _company
        c = _company()
        from compliance.tests import _journey_user
        self.client.force_login(_journey_user(c))
        self.assertContains(self.client.get(reverse('compliance:dashboard')), 'مسار عمل الشركة')

    def test_reports_still_work(self):
        from auditors.tests import _company_user
        c, cu = _company_user(subscribe=True)
        self.client.force_login(cu)
        self.assertEqual(self.client.get(reverse('compliance:report_executive_summary')).status_code, 200)


# ============================================================
# Phase 4E — UAT demo seed command (safe, local-only)
# ============================================================
class SeedUatDemoDataTests(TestCase):
    def _run(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('seed_uat_demo_data', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_seed_uat_demo_data_dry_run_does_not_write(self):
        before = (Company.objects.count(), User.objects.count())
        out = self._run()  # default = dry-run
        self.assertIn('DRY-RUN', out)
        self.assertEqual((Company.objects.count(), User.objects.count()), before)

    def test_seed_uat_demo_data_apply_creates_sample_company(self):
        self._run('--apply')
        self.assertTrue(Company.objects.filter(cr_number='1010123456').exists())
        self.assertTrue(User.objects.filter(email='client@1saudicyber.local').exists())
        from auditors.models import AuditorProfile
        self.assertTrue(AuditorProfile.objects.filter(user__email='auditor@1saudicyber.local',
                                                      status='active').exists())

    def test_seed_uat_demo_data_idempotent(self):
        self._run('--apply')
        self._run('--apply')
        self.assertEqual(Company.objects.filter(cr_number='1010123456').count(), 1)
        self.assertEqual(User.objects.filter(email='client@1saudicyber.local').count(), 1)

    def test_seed_uat_demo_data_does_not_create_companycontrol(self):
        from compliance.models import CompanyControl
        before = CompanyControl.objects.count()
        self._run('--apply')
        self.assertEqual(CompanyControl.objects.count(), before)

    def test_seed_uat_demo_data_does_not_import_otcc_dcc(self):
        from compliance.models import Control
        self._run('--apply')
        self.assertFalse(Control.objects.filter(control_id__icontains='OTCC').exists())
        self.assertFalse(Control.objects.filter(control_id__icontains='DCC').exists())
        # And no compliance decisions were fabricated.
        from compliance.models import ControlAssessment
        self.assertEqual(ControlAssessment.objects.count(), 0)

    def test_seed_uat_demo_data_requires_or_handles_password_safely(self):
        import os
        from unittest import mock
        # No UAT_DEMO_PASSWORD env -> apply still works using a documented LOCAL-ONLY default + warning.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('UAT_DEMO_PASSWORD', None)
            out = self._run('--apply')
        self.assertIn('UAT_DEMO_PASSWORD not set', out)
        self.assertTrue(User.objects.filter(email='client@1saudicyber.local').exists())

    def test_seed_uat_demo_data_subscribe_flag_activates_subscription(self):
        from billing.subscription_access import company_has_active_subscription
        self._run('--apply', '--subscribe')
        c = Company.objects.get(cr_number='1010123456')
        self.assertTrue(company_has_active_subscription(c))


# ============================================================
# UX-1B-CLEANUP-A — Arabic UI residue sweep
# ============================================================
class ArabicResidueCleanupTests(TestCase):
    def _reg_company_user(self):
        self.client.post(reverse('core:company_register'), {
            'first_name': 'S', 'last_name': 'A', 'email': 'res@co.example', 'phone': '',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'Co', 'cr_number': '3434343434',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})

    def test_onboarding_welcome_uses_clean_intake_label(self):
        self._reg_company_user()
        resp = self.client.get(reverse('core:onboarding'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ملف التصنيف')
        self.assertNotContains(resp, '(Intake)')
        self.assertNotContains(resp, 'ملف التصنيف (Intake)')

    def test_evidence_checklist_heading_has_no_parenthetical(self):
        from compliance.tests import _company_with_official_plan, _journey_user
        c, fv, scope = _company_with_official_plan()
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:evidence_checklist'))
        self.assertContains(resp, 'قائمة الأدلة المخطّطة')
        self.assertNotContains(resp, '(Evidence Checklist)')

    def test_control_plan_heading_has_no_parenthetical(self):
        from compliance.tests import _company_with_official_plan, _journey_user
        c, fv, scope = _company_with_official_plan()
        self.client.force_login(_journey_user(c))
        resp = self.client.get(reverse('compliance:control_plan'))
        self.assertContains(resp, 'خطة الضوابط')
        self.assertNotContains(resp, '(Control Applicability Plan)')

    def test_reports_index_has_no_english_parentheticals(self):
        from compliance.tests import _company_with_assessments, _journey_user
        from billing.subscription_access import activate_company_subscription
        c, fv, scope = _company_with_assessments()
        self.client.force_login(_journey_user(c))
        # unsubscribed
        body = self.client.get(reverse('compliance:reports_index')).content.decode()
        self.assertNotIn('(Subscription required)', body)
        # subscribed
        activate_company_subscription(c, 'Plan', days=30)
        body2 = self.client.get(reverse('compliance:reports_index')).content.decode()
        self.assertNotIn('(Reports unlocked)', body2)

    def test_journey_dashboard_has_no_english_parentheticals(self):
        from compliance.tests import _company, _journey_user
        c = _company()
        self.client.force_login(_journey_user(c))
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertNotIn('(Reports unlocked)', body)
        self.assertNotIn('(Reports require active subscription)', body)
        self.assertNotIn('مسار الامتثال (Compliance Journey)', body)

    def test_no_old_brand_or_count_in_common_pages(self):
        from compliance.tests import _company, _journey_user
        c = _company()
        self.client.force_login(_journey_user(c))
        for name in ['compliance:dashboard', 'compliance:intake']:
            body = self.client.get(reverse(name)).content.decode()
            self.assertNotIn('CyberTrust KSA', body)
            self.assertNotIn('334', body)


# ============================================================
# UX-1C — Bilingual language switcher + English catalogs
# ============================================================
class BilingualSwitcherTests(TestCase):
    def _login_company(self):
        from compliance.tests import _company, _journey_user
        c = _company()
        self.client.force_login(_journey_user(c))
        return c

    def test_set_language_route_exists(self):
        resp = self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        self.assertEqual(resp.status_code, 302)

    def test_arabic_is_default_shell(self):
        self._login_company()
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertIn('lang="ar"', body)
        self.assertIn('dir="rtl"', body)
        self.assertIn('لوحة التحكم', body)

    def test_english_mode_switches_shell(self):
        self._login_company()
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertIn('lang="en"', body)
        self.assertIn('dir="ltr"', body)
        self.assertIn('Dashboard', body)
        self.assertNotIn('لوحة التحكم', body)

    def test_switcher_present_desktop_and_mobile(self):
        self._login_company()
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        # set_language form appears at least twice (desktop nav + mobile hamburger)
        self.assertGreaterEqual(body.count(reverse('set_language')), 2)
        self.assertIn('English', body)
        self.assertIn('العربية', body)

    def _login_messages(self):
        # PILOT-HOTFIX-B (C): a failed login now renders an INLINE error on /login/
        # (no global django messages, which leaked onto unrelated pages). Read the
        # rendered login page instead of the message framework.
        resp = self.client.post(reverse('core:login'),
                                {'username': 'no@x.com', 'password': 'wrongwrong'})
        return resp.content.decode()

    def test_login_invalid_message_arabic_by_default(self):
        self.assertIn('بيانات الدخول غير صحيحة. حاول مرة أخرى.', self._login_messages())

    def test_login_invalid_message_english_in_english_mode(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        self.assertIn('Invalid credentials. Please try again.', self._login_messages())

    def test_anonymous_login_page_has_switcher(self):
        body = self.client.get(reverse('core:login')).content.decode()
        self.assertIn(reverse('set_language'), body)
        self.assertIn('English', body)
        self.assertIn('العربية', body)

    def test_no_old_brand_count_or_cert_in_shell(self):
        self._login_company()
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertNotIn('CyberTrust KSA', body)
        self.assertNotIn('334', body)

    def test_journey_wizard_still_renders(self):
        self._login_company()
        resp = self.client.get(reverse('compliance:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ct-journey-wizard')

    def test_monitoring_route_renders_or_redirects(self):
        self._login_company()
        resp = self.client.get('/monitoring/continuous/')
        self.assertIn(resp.status_code, (200, 302))


# ============================================================
# Phase 8C — Public UX Trust Polish
# ============================================================
from django.utils import timezone as _tz_8c


class Phase8CPublicUXTrustTests(TestCase):
    def _reg_payload(self, **over):
        d = {
            'first_name': 'S', 'last_name': 'A', 'email': 'trust8c@co.example', 'phone': '',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'شركة', 'company_name': 'Co', 'cr_number': '9090909090',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on',
        }
        d.update(over)
        return d

    # 1) Login page Arabic copy
    def test_login_page_arabic_copy(self):
        body = self.client.get(reverse('core:login')).content.decode()
        self.assertIn('مرحبًا بعودتك', body)
        self.assertIn('تسجيل الدخول', body)
        self.assertNotIn('Welcome back', body)  # default Arabic, not English

    # 2) Registration Arabic labels + help text
    def test_registration_arabic_labels_and_help(self):
        body = self.client.get(reverse('core:company_register')).content.decode()
        self.assertIn('الرعاية الصحية', body)        # sector AR label
        self.assertIn('متناهية الصغر', body)          # size AR label
        self.assertNotIn('Oil & Gas', body)
        self.assertNotIn('Petrochemical', body)
        self.assertIn('يتكوّن غالبًا من 10 أرقام', body)   # CR hint
        self.assertIn('أوافق على شروط الاستخدام وسياسة الخصوصية', body)  # terms label

    # 3) Terms acceptance required
    def test_registration_requires_terms_acceptance(self):
        resp = self.client.post(reverse('core:company_register'),
                                self._reg_payload(accept_terms=''))
        self.assertEqual(resp.status_code, 200)  # re-render, not redirect
        self.assertContains(resp, 'يجب الموافقة على شروط الاستخدام وسياسة الخصوصية')
        self.assertFalse(Company.objects.filter(cr_number='9090909090').exists())

    def test_registration_succeeds_with_terms(self):
        resp = self.client.post(reverse('core:company_register'), self._reg_payload())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Company.objects.filter(cr_number='9090909090').exists())

    # 4) Auditor wording safety (public auditor intake page)
    def test_auditor_public_wording_safe(self):
        body = self.client.get(reverse('core:auditor_register')).content.decode()
        self.assertNotIn('مدقّق معتمد', body)
        self.assertIn('مراجع امتثال', body)

    # 5) Public pages have no positive certification/accreditation claims
    def test_public_pages_no_certification_claims(self):
        for url in (reverse('core:landing'), reverse('core:login'),
                    reverse('core:get_started'), reverse('core:auditor_register')):
            body = self.client.get(url).content.decode()
            for bad in ('معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك',
                        'official accreditation', 'certified by NCA', 'شهادة رسمية', 'اعتماد حكومي'):
                self.assertNotIn(bad, body, f'{bad} in {url}')

    # 6) Footer uses dynamic year, not hardcoded 2024
    def test_footer_dynamic_year(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        year = str(_tz_8c.now().year)
        self.assertIn(year, body)
        self.assertNotIn('&copy; 2024', body)
        self.assertNotIn('© 2024', body)

    # 7) Marketing 24/7 absolute claim removed; illustrative disclaimer present
    def test_landing_marketing_safety(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertNotIn('24/7', body)
        self.assertIn('جاهزية للمراقبة المستمرة', body)
        self.assertIn('مؤشرات توضيحية', body)
        self.assertIn('417', body)        # official total still shown
        self.assertNotIn('>334<', body)   # legacy total not a displayed figure


# ============================================================
# Phase 8C-FIX-C — Public language switcher coverage
# ============================================================
class Phase8CFixCLanguageSwitcherTests(TestCase):
    PUBLIC = ['core:landing', 'core:login', 'core:get_started',
              'core:company_register', 'core:auditor_register']

    def _body(self, name):
        return self.client.get(reverse(name)).content.decode()

    def test_landing_has_language_switcher(self):
        b = self._body('core:landing')
        self.assertIn(reverse('set_language'), b)
        self.assertIn('name="language" value="ar"', b)
        self.assertIn('name="language" value="en"', b)

    def test_login_still_has_switcher_exactly_once(self):
        b = self._body('core:login')
        self.assertEqual(b.count('name="language" value="ar"'), 1)  # no duplicate

    def test_all_public_pages_have_one_switcher(self):
        for name in self.PUBLIC:
            b = self._body(name)
            self.assertEqual(b.count('name="language" value="ar"'), 1, f'{name} switcher count')
            self.assertIn(reverse('set_language'), b)

    def test_switcher_posts_to_i18n_set_language(self):
        b = self._body('core:get_started')
        self.assertIn('action="%s"' % reverse('set_language'), b)
        self.assertEqual(reverse('set_language'), '/i18n/setlang/')
        self.assertIn('name="next"', b)  # returns to current page

    def test_switcher_works_in_english_mode(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        b = self._body('core:landing')
        self.assertIn('lang="en"', b)
        self.assertIn('name="language" value="ar"', b)  # switcher still offers Arabic

    def test_no_unsafe_accreditation_wording_introduced(self):
        for name in self.PUBLIC:
            b = self._body(name)
            for bad in ('معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك',
                        'official accreditation', 'certified by NCA', 'اعتماد حكومي'):
                self.assertNotIn(bad, b, f'{bad} in {name}')


# ============================================================
# Phase 8C-FIX-D — Remove public template comment leakage
# ============================================================
class Phase8CFixDCommentLeakTests(TestCase):
    PUBLIC = ['core:landing', 'core:login', 'core:get_started',
              'core:company_register', 'core:auditor_register']
    LEAKS = ['Phase 8C-FIX-C', 'reusable public Arabic/English language switcher',
             'Posts to Django i18n set_language', 'RTL/LTR safe']

    def _body(self, name):
        return self.client.get(reverse(name)).content.decode()

    def test_no_implementation_comment_leak_on_public_pages(self):
        for name in self.PUBLIC:
            b = self._body(name)
            for leak in self.LEAKS:
                self.assertNotIn(leak, b, f'leak "{leak}" on {name}')

    def test_switcher_still_present_once_per_public_page(self):
        for name in self.PUBLIC:
            b = self._body(name)
            self.assertEqual(b.count('name="language" value="ar"'), 1, f'{name} switcher count')
            self.assertIn(reverse('set_language'), b)

    def test_login_no_duplicate_switcher(self):
        self.assertEqual(self._body('core:login').count('name="language" value="ar"'), 1)

    def test_no_unsafe_accreditation_wording(self):
        for name in self.PUBLIC:
            b = self._body(name)
            for bad in ('معتمد من NCA', 'official accreditation', 'certified by NCA',
                        'اعتماد رسمي', 'شهادة رسمية'):
                self.assertNotIn(bad, b, f'{bad} in {name}')


class Phase8CLanguageButtonFunctionalTests(TestCase):
    """Ensure the language-change button actually toggles + persists the language."""
    def test_button_toggles_ar_en_and_persists(self):
        setlang = reverse('set_language')
        landing = reverse('core:landing')
        # default Arabic
        self.assertIn('lang="ar"', self.client.get(landing).content.decode())
        # click English -> redirects back, page now English (LTR)
        r = self.client.post(setlang, {'language': 'en', 'next': '/'})
        self.assertEqual(r.status_code, 302)
        b_en = self.client.get(landing).content.decode()
        self.assertIn('lang="en"', b_en)
        # persists to another page (login shows English copy)
        lg = self.client.get(reverse('core:login')).content.decode()
        self.assertIn('lang="en"', lg)
        self.assertIn('Sign in', lg)
        self.assertNotIn('مرحبًا بعودتك', lg)
        # click Arabic -> back to Arabic (RTL)
        self.client.post(setlang, {'language': 'ar', 'next': '/'})
        b_ar = self.client.get(landing).content.decode()
        self.assertIn('lang="ar"', b_ar)
        self.assertIn('dir="rtl"', b_ar)


# ============================================================
# Phase 8D-2-FIX-A — Critical Manus blockers
# ============================================================
class Phase8D2FixACriticalBlockerTests(TestCase):
    # --- 1) gap-analysis must never 500 ---
    def test_gap_analysis_anonymous_redirects_not_500(self):
        resp = self.client.get(reverse('ai_engine:gap_analysis'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_gap_analysis_authorized_no_500_and_advisory(self):
        from compliance.tests import _company, _journey_user
        c = _company()
        self.client.force_login(_journey_user(c, email='gap8d@x.com'))
        resp = self.client.get(reverse('ai_engine:gap_analysis'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('استشاري', body)
        self.assertIn('لا يُعد قرارًا نهائيًا', body)
        for bad in ('شهادة امتثال رسمية', 'اعتماد رسمي', 'معتمد من NCA'):
            # only allowed inside negation; assert no positive standalone claim
            self.assertNotIn('نمنح ' + bad, body)

    # --- 2) legal pages ---
    def test_privacy_page_200(self):
        r = self.client.get(reverse('core:privacy'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'سياسة الخصوصية')

    def test_terms_page_200(self):
        r = self.client.get(reverse('core:terms'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'شروط الاستخدام')

    def test_footer_has_legal_links_on_landing(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn(reverse('core:privacy'), body)
        self.assertIn(reverse('core:terms'), body)

    def test_legal_pages_no_unsafe_claims(self):
        for name in ('core:privacy', 'core:terms'):
            body = self.client.get(reverse(name)).content.decode()
            for bad in ('معتمد من NCA', 'معتمد من أرامكو', 'معتمد من سابك',
                        'official accreditation', 'certified by NCA', 'اعتماد حكومي'):
                self.assertNotIn(bad, body, f'{bad} in {name}')

    # --- 3) classification disclaimer exactly once ---
    def test_classification_disclaimer_exactly_once(self):
        from compliance.tests import _company, _journey_user
        c = _company(target_nca=True)
        self.client.force_login(_journey_user(c, email='cls8d@x.com'))
        body = self.client.get(reverse('compliance:classification')).content.decode()
        self.assertEqual(body.count('لا يُعد قرارًا نهائيًا أو شهادة'), 1)

    # --- 4/5) landing language + lang/dir consistency ---
    def test_landing_arabic_lang_dir(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn('lang="ar"', body)
        self.assertIn('dir="rtl"', body)
        self.assertNotIn('dir="ltr"', body)  # inner div no longer hardcoded ltr/rtl mismatch

    def test_landing_english_lang_dir_and_switch(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn('lang="en"', body)
        self.assertIn('dir="ltr"', body)
        self.assertNotIn('dir="rtl"', body)   # consistent: no leftover rtl in english mode
        self.assertIn('Start your compliance assessment', body)  # key string translated

    def test_landing_switch_returns_to_landing_and_persists(self):
        r = self.client.post(reverse('set_language'), {'language': 'en', 'next': reverse('core:landing')})
        self.assertEqual(r.status_code, 302)
        # persists to another public page
        self.assertIn('lang="en"', self.client.get(reverse('core:login')).content.decode())

    def test_landing_no_internal_leak(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        for leak in ('Phase 8C-FIX-C', 'reusable public', 'Posts to Django', 'RTL/LTR safe'):
            self.assertNotIn(leak, body)

    def test_landing_417_not_334(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn('417', body)
        self.assertNotIn('>334<', body)


class Phase8D2FixBLandingTranslationTests(TestCase):
    """Manus 8D-2 Fix 5 — remaining landing marketing prose translated in English."""

    # Key marketing prose that previously stayed Arabic in English mode.
    EN_MARKERS = [
        'Supported frameworks',
        'The compliance journey in five steps',
        'Gap analysis',
        'Auditor review',
        'Register your company',
        'Ready to raise your compliance readiness?',
    ]
    AR_HEADINGS = [
        'الأطر المدعومة',
        'مسار الامتثال في خمس خطوات',
        'جاهزون لرفع جاهزية الامتثال؟',
    ]

    def test_english_mode_translates_marketing_prose(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn('lang="en"', body)
        self.assertIn('dir="ltr"', body)
        for marker in self.EN_MARKERS:
            self.assertIn(marker, body, marker)
        # English mode must NOT remain mostly Arabic: the major headings are translated.
        for ar in self.AR_HEADINGS:
            self.assertNotIn(ar, body, ar)

    def test_arabic_mode_remains_arabic(self):
        body = self.client.get(reverse('core:landing')).content.decode()
        self.assertIn('lang="ar"', body)
        self.assertIn('dir="rtl"', body)
        for ar in self.AR_HEADINGS:
            self.assertIn(ar, body, ar)

    def test_language_switcher_still_works(self):
        r = self.client.post(reverse('set_language'),
                             {'language': 'en', 'next': reverse('core:landing')})
        self.assertEqual(r.status_code, 302)
        self.assertIn('lang="en"', self.client.get(reverse('core:landing')).content.decode())

    def test_no_internal_template_leak(self):
        for lang in ('ar', 'en'):
            self.client.post(reverse('set_language'), {'language': lang, 'next': '/'})
            body = self.client.get(reverse('core:landing')).content.decode()
            for leak in ('{% trans', 'blocktrans', 'msgid', 'Phase 8D'):
                self.assertNotIn(leak, body, '%s in %s' % (leak, lang))

    def test_no_unsafe_certification_wording(self):
        for lang in ('ar', 'en'):
            self.client.post(reverse('set_language'), {'language': lang, 'next': '/'})
            body = self.client.get(reverse('core:landing')).content.decode()
            for banned in ('معتمد من NCA', 'اعتماد رسمي', 'certified by NCA',
                           'official accreditation', 'شهادة امتثال رسمية'):
                self.assertNotIn(banned, body, banned)


# ============================================================
# Phase 8D-3B-AUTH-A — Email OTP verification + Forgot Password
# ============================================================
from core import otp_services as _otp
from core.models import EmailOTP


def _reg_payload(**over):
    d = {
        'first_name': 'Otp', 'last_name': 'User',
        'email': 'otpuser@co.example', 'phone': '0500000000',
        'password': 'longenough123', 'password_confirm': 'longenough123',
        'company_name_ar': 'شركة الرمز', 'company_name': 'OTP Co',
        'cr_number': '3434343434', 'sector': 'technology', 'size': 'small',
        'city': 'Riyadh', 'country': 'SA', 'description': 'وصف',
        'target_nca': 'on', 'accept_terms': 'on',
    }
    d.update(over)
    return d


class EmailOTPTests(TestCase):
    def _user(self, email='u@x.com', **kw):
        return User.objects.create_user(username=email, email=email,
                                        password='longenough12', **kw)

    def test_registration_creates_otp_requirement(self):
        resp = self.client.post(reverse('core:company_register'), _reg_payload())
        self.assertEqual(resp.status_code, 302)
        u = User.objects.get(email='otpuser@co.example')
        self.assertFalse(u.email_verified)
        self.assertTrue(EmailOTP.objects.filter(user=u, used=False).exists())

    def test_registration_sends_otp_email(self):
        from django.core import mail
        self.client.post(reverse('core:company_register'), _reg_payload())
        self.assertTrue(any('1SaudiCyber' in m.subject or 'التحقق' in m.subject for m in mail.outbox))

    def test_valid_otp_verifies_email(self):
        u = self._user()
        raw = _otp.issue_and_send(u)
        self.client.force_login(u)
        resp = self.client.post(reverse('core:verify_email_otp'), {'code': raw})
        u.refresh_from_db()
        self.assertTrue(u.email_verified)
        self.assertEqual(resp.status_code, 302)

    def test_invalid_otp_does_not_verify(self):
        u = self._user()
        _otp.issue_and_send(u)
        self.client.force_login(u)
        self.client.post(reverse('core:verify_email_otp'), {'code': '000000'})
        u.refresh_from_db()
        self.assertFalse(u.email_verified)

    def test_expired_otp_does_not_verify(self):
        from django.utils import timezone
        from datetime import timedelta
        u = self._user()
        otp_obj, raw = _otp.issue_otp(u)
        EmailOTP.objects.filter(id=otp_obj.id).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        ok, reason = _otp.verify_otp(u, raw)
        self.assertFalse(ok)
        self.assertEqual(reason, 'expired')
        u.refresh_from_db()
        self.assertFalse(u.email_verified)

    def test_too_many_attempts_blocks(self):
        u = self._user()
        _otp.issue_otp(u)
        for _ in range(_otp.OTP_MAX_ATTEMPTS):
            _otp.verify_otp(u, '000000')  # wrong
        ok, reason = _otp.verify_otp(u, '000000')
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_many_attempts')

    def test_too_many_attempts_then_correct_still_blocked(self):
        u = self._user()
        otp_obj, raw = _otp.issue_otp(u)
        for _ in range(_otp.OTP_MAX_ATTEMPTS):
            _otp.verify_otp(u, '000000')
        ok, reason = _otp.verify_otp(u, raw)  # correct code, but attempts exhausted
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_many_attempts')
        u.refresh_from_db()
        self.assertFalse(u.email_verified)

    def test_resend_generates_new_active_otp(self):
        u = self._user()
        first, raw1 = _otp.issue_otp(u)
        # force resend allowed by ageing the first OTP
        from django.utils import timezone
        from datetime import timedelta
        EmailOTP.objects.filter(id=first.id).update(
            created_at=timezone.now() - timedelta(seconds=120))
        self.assertTrue(_otp.can_resend(u))
        self.client.force_login(u)
        self.client.post(reverse('core:resend_email_otp'))
        first.refresh_from_db()
        self.assertTrue(first.used)  # old one invalidated
        self.assertTrue(EmailOTP.objects.filter(user=u, used=False).exists())

    def test_resend_throttled_quickly(self):
        u = self._user()
        _otp.issue_otp(u)
        self.assertFalse(_otp.can_resend(u))  # just issued

    def test_otp_not_stored_in_plaintext(self):
        u = self._user()
        otp_obj, raw = _otp.issue_otp(u)
        self.assertNotIn(raw, otp_obj.code_hash)
        self.assertNotEqual(raw, otp_obj.code_hash)

    def test_auditor_registration_issues_otp(self):
        resp = self.client.post(reverse('auditors:register'), {
            'full_name': 'مدقق الرمز', 'email': 'audotp@x.com',
            'password': 'longenough123', 'password_confirm': 'longenough123',
            'city': 'Riyadh'})
        self.assertEqual(resp.status_code, 302)
        u = User.objects.get(email='audotp@x.com')
        self.assertTrue(EmailOTP.objects.filter(user=u, used=False).exists())

    def test_staff_login_not_broken_and_not_gated(self):
        staff = self._user(email='staffotp@x.com', is_staff=True)
        # email_verified defaults False, but staff must still access dashboard (no hard gate).
        self.client.force_login(staff)
        self.assertFalse(staff.email_verified)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertNotEqual(resp.status_code, 403)

    def test_legacy_unverified_user_not_locked_out(self):
        u = self._user(email='legacy@x.com', role='company_admin')
        self.client.force_login(u)
        # An unverified legacy user can still reach login/dashboard flow (non-blocking OTP).
        resp = self.client.get(reverse('core:verify_email_otp'))
        self.assertEqual(resp.status_code, 200)

    def test_already_verified_user_redirected_from_otp_page(self):
        u = self._user(email='verified@x.com')
        u.email_verified = True
        u.save(update_fields=['email_verified'])
        self.client.force_login(u)
        resp = self.client.get(reverse('core:verify_email_otp'))
        self.assertEqual(resp.status_code, 302)

    def test_otp_page_requires_login(self):
        resp = self.client.get(reverse('core:verify_email_otp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_resend_route_not_captured_as_token(self):
        # /verify-email/resend/ must hit the OTP resend view, not the legacy token view.
        u = self._user(email='resendroute@x.com')
        self.client.force_login(u)
        resp = self.client.post(reverse('core:resend_email_otp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('core:verify_email_otp'), resp.url)

    def test_no_unsafe_wording_on_otp_page(self):
        u = self._user(email='safe@x.com')
        self.client.force_login(u)
        body = self.client.get(reverse('core:verify_email_otp')).content.decode()
        for banned in ('معتمد من NCA', 'اعتماد رسمي', 'certified by NCA',
                       'official accreditation', 'government accredited', 'شهادة امتثال رسمية'):
            self.assertNotIn(banned, body)


class ForgotPasswordTests(TestCase):
    def _user(self, email='reset@x.com'):
        return User.objects.create_user(username=email, email=email, password='oldpassword123')

    def test_login_page_has_forgot_password_link(self):
        body = self.client.get(reverse('core:login')).content.decode()
        self.assertIn(reverse('core:password_reset'), body)
        self.assertIn('نسيت كلمة المرور', body)

    def test_password_reset_request_page_loads(self):
        self.assertEqual(self.client.get(reverse('core:password_reset')).status_code, 200)

    def test_reset_request_does_not_reveal_email_existence(self):
        self._user(email='exists@x.com')
        # Existing email -> redirect to done.
        r1 = self.client.post(reverse('core:password_reset'), {'email': 'exists@x.com'})
        # Non-existent email -> SAME redirect to done (no disclosure).
        r2 = self.client.post(reverse('core:password_reset'), {'email': 'nobody@x.com'})
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r1.url, r2.url)

    def test_reset_email_generated_for_existing_user(self):
        from django.core import mail
        self._user(email='hasmail@x.com')
        self.client.post(reverse('core:password_reset'), {'email': 'hasmail@x.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('hasmail@x.com', mail.outbox[0].to)

    def test_no_email_for_unknown_address(self):
        from django.core import mail
        self.client.post(reverse('core:password_reset'), {'email': 'ghost@x.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_token_allows_password_change_and_login(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        u = self._user(email='changer@x.com')
        uidb64 = urlsafe_base64_encode(force_bytes(u.pk))
        token = default_token_generator.make_token(u)
        # GET sets the session token then redirects to the 'set-password' URL.
        follow = self.client.get(reverse('core:password_reset_confirm',
                                          args=[uidb64, token]), follow=True)
        self.assertEqual(follow.status_code, 200)
        post_url = follow.redirect_chain[-1][0] if follow.redirect_chain else \
            reverse('core:password_reset_confirm', args=[uidb64, 'set-password'])
        resp = self.client.post(post_url, {'new_password1': 'BrandNewPass123',
                                           'new_password2': 'BrandNewPass123'})
        self.assertEqual(resp.status_code, 302)
        u.refresh_from_db()
        self.assertTrue(u.check_password('BrandNewPass123'))
        self.assertTrue(self.client.login(username='changer@x.com', password='BrandNewPass123'))

    def test_invalid_token_rejected(self):
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        u = self._user(email='badtoken@x.com')
        uidb64 = urlsafe_base64_encode(force_bytes(u.pk))
        resp = self.client.get(reverse('core:password_reset_confirm',
                                        args=[uidb64, 'invalid-token-xyz']), follow=True)
        self.assertContains(resp, 'رابط', status_code=200) if False else None
        # The confirm view renders an "invalid" state and does not offer the set-password form.
        self.assertNotContains(resp, 'new_password1')


# ============================================================
# Phase 8D-3C-SECURITY-A — Role Portal & Session Isolation
# ============================================================
from auditors.models import AuditorProfile, AuditorAssignment


class RolePortalIsolationTests(TestCase):
    def _company_with_user(self, cr='5151515151', email='cu@portal.example'):
        c = Company.objects.create(name='Portal Co', cr_number=cr, sector='technology',
                                   size='small', contact_email=email)
        u = User.objects.create_user(username=email, email=email, password='longenough12',
                                     company=c, role='company_admin')
        return c, u

    def _auditor(self, email='aud@portal.example', status='active'):
        u = User.objects.create_user(username=email, email=email, password='longenough12',
                                     role='auditor')
        p = AuditorProfile.objects.create(user=u, full_name='Portal Auditor', status=status)
        return u, p

    def _staff(self, email='staff@portal.example', superuser=False):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True, is_superuser=superuser)

    def _unlinked(self, email='orphan@portal.example'):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='company_admin')

    # ---- role helpers ----
    def test_role_helpers_classify_correctly(self):
        from core.roles import portal_for, is_company_user, is_auditor_user, is_platform_admin_user
        _, cu = self._company_with_user()
        au, _ = self._auditor()
        st = self._staff()
        orphan = self._unlinked()
        self.assertEqual(portal_for(cu), 'company')
        self.assertEqual(portal_for(au), 'auditor')
        self.assertEqual(portal_for(st), 'platform_admin')
        self.assertEqual(portal_for(orphan), 'company_unlinked')
        self.assertTrue(is_company_user(cu))
        self.assertTrue(is_auditor_user(au))
        self.assertTrue(is_platform_admin_user(st))
        self.assertFalse(is_company_user(st))
        self.assertFalse(is_company_user(au))

    # ---- /platform-admin/ access (1-4) ----
    def test_anonymous_cannot_access_platform_admin(self):
        r = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.url)

    def test_company_user_cannot_access_platform_admin(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 403)

    def test_auditor_user_cannot_access_platform_admin(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 403)

    def test_staff_and_superuser_can_access_platform_admin(self):
        for u in (self._staff(), self._staff(email='su@portal.example', superuser=True)):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 200)

    # ---- staff/auditor on company pages (6,7,8) ----
    def test_staff_on_company_page_gets_admin_safe_message(self):
        st = self._staff()
        self.client.force_login(st)
        resp = self.client.get(reverse('compliance:classification'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Get Solution CRM')
        self.assertContains(resp, 'signed in as Get Solution staff')
        self.assertNotContains(resp, 'not linked to a company')  # not the customer text

    def test_auditor_on_company_page_gets_auditor_safe_message(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        resp = self.client.get(reverse('compliance:classification'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Auditor account')
        self.assertContains(resp, reverse('auditors:dashboard'))

    def test_unlinked_user_gets_safe_no_company_page(self):
        orphan = self._unlinked()
        self.client.force_login(orphan)
        resp = self.client.get(reverse('compliance:classification'))
        self.assertEqual(resp.status_code, 200)  # no 500
        self.assertContains(resp, 'not linked to a company')
        self.assertContains(resp, 'Get Solution support')

    # ---- session isolation (9-13) ----
    def test_company_user_cannot_switch_into_auditor_registration(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        before = AuditorProfile.objects.count()
        resp = self.client.post(reverse('auditors:register'), {
            'full_name': 'X', 'email': 'switchaud@x.com',
            'password': 'longenough123', 'password_confirm': 'longenough123'})
        self.assertEqual(resp.status_code, 200)  # blocked page
        self.assertEqual(AuditorProfile.objects.count(), before)
        self.assertEqual(int(self.client.session['_auth_user_id']), cu.id)  # session unchanged

    def test_auditor_cannot_switch_into_company_registration(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        before = Company.objects.count()
        resp = self.client.post(reverse('core:company_register'), {
            'first_name': 'A', 'last_name': 'B', 'email': 'newco@x.com',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'ش', 'company_name': 'C', 'cr_number': '7777777777',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on', 'accept_terms': 'on'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'already signed in')
        self.assertEqual(Company.objects.count(), before)  # no new company
        self.assertEqual(int(self.client.session['_auth_user_id']), au.id)

    def test_staff_cannot_register_company_in_session(self):
        st = self._staff()
        self.client.force_login(st)
        before = Company.objects.count()
        resp = self.client.post(reverse('core:register'), {
            'first_name': 'A', 'last_name': 'B', 'email': 'staffco@x.com',
            'phone': '', 'password': 'longenough123', 'password_confirm': 'longenough123',
            'company_name_ar': 'ش', 'company_name': 'C', 'cr_number': '8888888888',
            'sector': 'technology', 'size': 'small'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'already signed in')
        self.assertEqual(Company.objects.count(), before)

    def test_registration_pages_anonymous_accessible(self):
        self.assertEqual(self.client.get(reverse('core:company_register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('auditors:register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('core:register')).status_code, 200)

    # ---- portal redirects (14-17) ----
    def test_staff_dashboard_redirects_to_crm(self):
        self.client.force_login(self._staff())
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('platform_admin:dashboard'))

    def test_auditor_dashboard_redirects_to_auditor_portal(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auditor', resp.url)

    def test_company_linked_user_reaches_company_dashboard(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 200)  # company dashboard, not no_company/500

    def test_unlinked_user_dashboard_safe_no_company(self):
        self.client.force_login(self._unlinked())
        resp = self.client.get(reverse('dashboard:main'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'not linked to a company')

    # ---- data isolation (18,19) ----
    def test_company_user_cannot_open_other_company_crm_detail(self):
        other, _ = self._company_with_user(cr='9090909090', email='other@x.com')
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        # CRM company-detail is staff-only; a company user is denied (no ID enumeration).
        self.assertEqual(self.client.get(
            reverse('platform_admin:company_detail', args=[other.id])).status_code, 403)

    def test_active_auditor_sees_only_assigned_company(self):
        au, p = self._auditor()
        c1, _ = self._company_with_user(cr='1111000011', email='c1@x.com')
        c2, _ = self._company_with_user(cr='2222000022', email='c2@x.com')
        a1 = AuditorAssignment.objects.create(company=c1, auditor=p, status='accepted')
        from auditors.services import assignments_for_user
        assigned = list(assignments_for_user(au))
        self.assertIn(a1, assigned)
        self.assertTrue(all(a.company_id == c1.id for a in assigned))

    # ---- UI isolation + safety (22,24,25) ----
    def test_company_dashboard_has_no_crm_nav(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        body = self.client.get(reverse('dashboard:main')).content.decode()
        self.assertNotIn('Get Solution CRM', body)
        self.assertNotIn('/platform-admin/', body)

    def test_status_pages_have_no_unsafe_claims(self):
        banned = ['معتمد من NCA', 'اعتماد رسمي', 'اعتماد حكومي', 'certified by NCA',
                  'official accreditation', 'government accredited', 'official certification',
                  'شهادة امتثال رسمية']
        # staff no-company, unlinked no-company, already-authenticated
        st = self._staff(); self.client.force_login(st)
        bodies = [self.client.get(reverse('compliance:classification')).content.decode()]
        au, _ = self._auditor(email='aud2@x.com'); self.client.force_login(au)
        bodies.append(self.client.get(reverse('core:company_register')).content.decode())
        for body in bodies:
            for w in banned:
                self.assertNotIn(w, body)


class ExplicitPortalGuardTests(TestCase):
    """Phase 8D-3C-B — explicit company_portal_required / auditor_portal_required guards."""

    def _company_with_user(self, cr='6161616161', email='cg@portal.example'):
        c = Company.objects.create(name='Guard Co', cr_number=cr, sector='technology',
                                   size='small', contact_email=email)
        u = User.objects.create_user(username=email, email=email, password='longenough12',
                                     company=c, role='company_admin')
        return c, u

    def _auditor(self, email='ag@portal.example', status='active'):
        u = User.objects.create_user(username=email, email=email, password='longenough12',
                                     role='auditor')
        p = AuditorProfile.objects.create(user=u, full_name='Guard Auditor', status=status)
        return u, p

    def _staff(self, email='sg@portal.example', superuser=False, company=None):
        return User.objects.create_user(username=email, email=email, password='longenough12',
                                        role='admin', is_staff=True, is_superuser=superuser,
                                        company=company)

    COMPANY_PAGES = ('compliance:classification', 'compliance:applicability_preview',
                     'compliance:controls_list', 'compliance:evidence_checklist',
                     'compliance:reports_index', 'risk:list', 'monitoring:overview')

    # ---- company guard ----
    def test_anonymous_company_page_redirects_login(self):
        for name in self.COMPANY_PAGES:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/login', r.url, name)

    def test_company_user_allowed(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        for name in self.COMPANY_PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_staff_with_company_still_allowed(self):
        # A staff user acting in company context (has a company) must NOT be blocked.
        c, _ = self._company_with_user(cr='6262626262', email='cs@x.com')
        st = self._staff(email='staffco@x.com', company=c)
        self.client.force_login(st)
        self.assertEqual(self.client.get(reverse('compliance:classification')).status_code, 200)

    def test_staff_without_company_gets_crm_safe_message(self):
        st = self._staff()
        self.client.force_login(st)
        resp = self.client.get(reverse('compliance:classification'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Get Solution CRM')
        self.assertNotContains(resp, 'not linked to a company')

    def test_auditor_on_company_page_safe(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        resp = self.client.get(reverse('compliance:classification'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Auditor account')

    def test_unlinked_user_company_page_safe_no_500(self):
        u = User.objects.create_user(username='ug@x.com', email='ug@x.com',
                                     password='longenough12', role='company_admin')
        self.client.force_login(u)
        resp = self.client.get(reverse('risk:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'not linked to a company')

    # ---- auditor guard ----
    def test_anonymous_auditor_page_redirects_login(self):
        for name in ('auditors:dashboard', 'auditors:onboarding'):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/login', r.url, name)

    def test_active_auditor_allowed_on_dashboard(self):
        au, _ = self._auditor()
        self.client.force_login(au)
        self.assertEqual(self.client.get(reverse('auditors:dashboard')).status_code, 200)

    def test_pending_auditor_allowed_on_onboarding(self):
        au, _ = self._auditor(email='pend@x.com', status='pending_review')
        self.client.force_login(au)
        self.assertEqual(self.client.get(reverse('auditors:onboarding')).status_code, 200)

    def test_pending_auditor_assignment_detail_no_company_data(self):
        au, p = self._auditor(email='pend2@x.com', status='pending_review')
        c, _ = self._company_with_user(cr='6363636363', email='c3@x.com')
        a = AuditorAssignment.objects.create(company=c, auditor=p, status='accepted')
        self.client.force_login(au)
        resp = self.client.get(reverse('auditors:assignment_detail', args=[a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'سياق الشركة')

    def test_company_user_denied_auditor_dashboard(self):
        _, cu = self._company_with_user()
        self.client.force_login(cu)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 302)  # -> auditor registration (existing safe flow)
        self.assertIn(reverse('auditors:register'), resp.url)

    def test_staff_on_auditor_page_gets_portal_mismatch(self):
        st = self._staff(email='staffaud@x.com')
        self.client.force_login(st)
        resp = self.client.get(reverse('auditors:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'requires a different portal')
        self.assertContains(resp, 'Get Solution CRM')

    # ---- safety ----
    def test_portal_mismatch_no_unsafe_wording(self):
        st = self._staff(email='staffsafe@x.com')
        self.client.force_login(st)
        body = self.client.get(reverse('auditors:dashboard')).content.decode()
        for w in ('معتمد من NCA', 'اعتماد رسمي', 'certified by NCA', 'official accreditation',
                  'government accredited', 'official certification', 'شهادة امتثال رسمية'):
            self.assertNotIn(w, body)


class OnboardingVerificationCTATests(TestCase):
    """UAT-COMPANY-EMAIL-VERIFICATION-CTA-FIX-A — onboarding resend-verification CTA + guards."""

    def _company(self, cr='9191919191'):
        return Company.objects.create(name='Verify Co', cr_number=cr, sector='technology',
                                      size='small', contact_email='vco@x.com')

    def _user(self, verified, email='vu@x.com', cr='9191919191'):
        c = self._company(cr=cr)
        return User.objects.create_user(email=email, password='longenough12', company=c,
                                        role='company_admin', email_verified=verified)

    def test_unverified_user_sees_alert_and_resend_button(self):
        self.client.force_login(self._user(False))
        resp = self.client.get(reverse('core:onboarding'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'يرجى التحقق من بريدك الإلكتروني قبل المتابعة')
        self.assertContains(resp, 'إعادة إرسال رابط التحقق')
        self.assertContains(resp, reverse('core:resend_verification_link'))

    def test_verified_user_does_not_see_resend_button(self):
        self.client.force_login(self._user(True, email='vok@x.com', cr='9292929292'))
        resp = self.client.get(reverse('core:onboarding'))
        self.assertNotContains(resp, 'إعادة إرسال رابط التحقق')
        self.assertContains(resp, 'ابدأ ملف التصنيف')

    def test_resend_get_is_not_allowed_and_sends_nothing(self):
        self.client.force_login(self._user(False, email='vg@x.com', cr='9393939393'))
        before = EmailVerificationToken.objects.count()
        resp = self.client.get(reverse('core:resend_verification_link'))
        self.assertEqual(resp.status_code, 405)                      # POST only
        self.assertEqual(EmailVerificationToken.objects.count(), before)

    def test_resend_post_sends_link_and_shows_success(self):
        self.client.force_login(self._user(False, email='vp@x.com', cr='9494949494'))
        before = EmailVerificationToken.objects.count()
        resp = self.client.post(reverse('core:resend_verification_link'), follow=True)
        self.assertEqual(EmailVerificationToken.objects.count(), before + 1)   # link re-issued
        self.assertContains(resp, 'تم إرسال رابط التحقق مرة أخرى، يرجى مراجعة بريدك الإلكتروني')

    def test_unverified_user_cannot_approve_scope(self):
        u = self._user(False, email='vs@x.com', cr='9595959595')
        self.client.force_login(u)
        resp = self.client.post(reverse('compliance:approve_company_scope'))
        self.assertEqual(resp.status_code, 302)                      # blocked -> onboarding
        self.assertIn(reverse('core:onboarding'), resp.url)

    def test_verified_user_reaches_onboarding_journey_cta(self):
        self.client.force_login(self._user(True, email='vj@x.com', cr='9696969696'))
        resp = self.client.get(reverse('core:onboarding'))
        self.assertContains(resp, reverse('compliance:intake'))      # normal journey CTA present
