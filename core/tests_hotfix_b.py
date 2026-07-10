"""PILOT-HOTFIX-B regression tests — admin safety/branding, login UX, password reset,
registration wizard, platform-admin data health, nav isolation, root redirects.

No payment/Moyasar changes. Reuses core fixtures only.
"""
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Company

User = get_user_model()


def _company(cr='9911223344', email='hb_co@x.com'):
    return Company.objects.create(name='HBCo', cr_number=cr, sector='technology',
                                  size='small', contact_email=email)


def _user(email, **kw):
    kw.setdefault('password', 'longenough12')
    kw.setdefault('role', 'company_admin')
    return User.objects.create_user(username=email, email=email, **kw)


# ---------------------------------------------------------------------------
# A) Django admin branding + password-hash safety
# ---------------------------------------------------------------------------
class AdminBrandingSafetyTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser(username='su@x.com', email='su@x.com',
                                                password='longenough12')
        self.client.force_login(self.su)

    def test_admin_branding_values(self):
        self.assertEqual(django_admin.site.site_header, 'Get Solution Company — 1SaudiCyber Admin')
        self.assertEqual(django_admin.site.site_title, 'Get Solution Company')
        self.assertEqual(django_admin.site.index_title, '1SaudiCyber Operations Administration')

    def test_user_change_password_is_not_raw_editable_field(self):
        target = _user('someuser@x.com', company=_company())
        resp = self.client.get(reverse('admin:core_user_change', args=[target.id]))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # ReadOnlyPasswordHashField renders a read-only display + a change-password link
        # (../password/), and never an editable <input name="password"> holding the hash.
        # (Language-agnostic: the help text is localized, the link path is not.)
        self.assertNotIn('name="password"', body)
        self.assertIn('password/', body)

    def test_mfa_secret_not_shown_in_user_admin(self):
        target = _user('mfauser@x.com', company=_company('9911223300', 'm@x.com'),
                       mfa_secret='TOPSECRETVALUE123')
        body = self.client.get(reverse('admin:core_user_change', args=[target.id])).content.decode()
        self.assertNotIn('TOPSECRETVALUE123', body)

    def test_critical_admin_changelists_load(self):
        for model in ('core_user', 'core_company', 'billing_plan', 'billing_payment',
                      'billing_companysubscription', 'compliance_controlgapassessment',
                      'auditors_companycrmprofile', 'auditors_companycrmnote'):
            resp = self.client.get(reverse('admin:%s_changelist' % model))
            self.assertEqual(resp.status_code, 200, model)


# ---------------------------------------------------------------------------
# C) Login UX — inline error, no message leak
# ---------------------------------------------------------------------------
class LoginUxTests(TestCase):
    def setUp(self):
        self.c = _company('9911220001', 'lg@x.com')
        self.u = _user('loginok@x.com', company=self.c)

    def test_wrong_password_shows_inline_error_200(self):
        resp = self.client.post(reverse('core:login'),
                                {'username': 'loginok@x.com', 'password': 'wrongwrong'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'غير صحيحة')
        self.assertContains(resp, 'loginok@x.com')          # email preserved
        self.assertNotContains(resp, 'wrongwrong')          # password never echoed

    def test_failed_login_error_not_leaked_to_password_reset(self):
        self.client.post(reverse('core:login'),
                         {'username': 'loginok@x.com', 'password': 'nope'})
        body = self.client.get(reverse('core:password_reset')).content.decode()
        self.assertNotIn('غير صحيحة', body)

    def test_repeated_failed_logins_do_not_accumulate(self):
        for _ in range(3):
            resp = self.client.post(reverse('core:login'),
                                    {'username': 'loginok@x.com', 'password': 'nope'})
        self.assertEqual(resp.content.decode().count('غير صحيحة'), 1)

    def test_valid_login_redirects(self):
        resp = self.client.post(reverse('core:login'),
                                {'username': 'loginok@x.com', 'password': 'longenough12'})
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# D) Password reset professional redesign
# ---------------------------------------------------------------------------
class PasswordResetUxTests(TestCase):
    def test_reset_request_page_is_professional(self):
        body = self.client.get(reverse('core:password_reset')).content.decode()
        self.assertIn('auth-card', body)
        self.assertIn('reset instructions if the account exists', body)
        self.assertNotIn('as_p', body)

    def test_unknown_email_shows_safe_done_page(self):
        resp = self.client.post(reverse('core:password_reset'),
                                {'email': 'nobody@nowhere.test'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'If an account exists')

    def test_confirm_invalid_token_safe_message(self):
        resp = self.client.get(reverse('core:password_reset_confirm',
                                        kwargs={'uidb64': 'AB', 'token': 'bad-token'}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'invalid or has expired')


# ---------------------------------------------------------------------------
# F) Registration wizard step-3 error state
# ---------------------------------------------------------------------------
class RegistrationWizardErrorTests(TestCase):
    def test_step3_error_keeps_user_on_step3(self):
        # Fill steps 1 & 2 validly but omit accept_terms (step 3) -> stays on step 3.
        data = {
            'first_name': 'A', 'last_name': 'B', 'email': 'wiz@x.com',
            'password': 'longenough12xX', 'password_confirm': 'longenough12xX',
            'company_name_ar': 'شركة', 'cr_number': '1231231231',
            'sector': 'technology', 'size': 'small', 'target_nca': 'on',
            # accept_terms intentionally missing
        }
        resp = self.client.post(reverse('core:company_register'), data)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('data-active-step="2"', body)             # server put us on step 3
        self.assertIn('class="ct-step active" data-step="2"', body)
        self.assertNotIn(' js-off', body)                       # not the collapse-all fallback
        self.assertNotIn('longenough12xX', body)                # password never echoed


# ---------------------------------------------------------------------------
# B) platform-admin data health + access control
# ---------------------------------------------------------------------------
class PlatformAdminDataHealthTests(TestCase):
    def test_staff_sees_data_health(self):
        staff = _user('pah_staff@x.com', is_staff=True, role='admin')
        self.client.force_login(staff)
        resp = self.client.get(reverse('platform_admin:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'صحة بيانات الأطر الرسمية')

    def test_company_user_denied_platform_admin(self):
        self.client.force_login(_user('pah_co@x.com', company=_company('9911220002', 'p@x.com')))
        self.assertEqual(self.client.get(reverse('platform_admin:dashboard')).status_code, 403)

    def test_dashboard_has_no_secret_strings(self):
        staff = _user('pah_staff2@x.com', is_staff=True, role='admin')
        self.client.force_login(staff)
        body = self.client.get(reverse('platform_admin:dashboard')).content.decode()
        for pat in ('sk_test_', 'sk_live_', 'MOYASAR_SECRET', 'SECRET_KEY'):
            self.assertNotIn(pat, body)


# ---------------------------------------------------------------------------
# H) Navigation role isolation (rendered on a base.html page every role can GET)
# ---------------------------------------------------------------------------
class NavIsolationTests(TestCase):
    def test_company_user_sees_no_platform_admin_nav(self):
        self.client.force_login(_user('nav_co@x.com', company=_company('9911220003', 'n@x.com')))
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertNotIn('/platform-admin/', body)

    def test_staff_sees_platform_admin_nav_not_company_journey(self):
        staff = _user('nav_staff@x.com', is_staff=True, role='admin')
        self.client.force_login(staff)
        body = self.client.get(reverse('billing:home')).content.decode()
        self.assertIn('/platform-admin/', body)


# ---------------------------------------------------------------------------
# I) Root route redirects
# ---------------------------------------------------------------------------
class RootRedirectTests(TestCase):
    def test_compliance_root_does_not_404_or_500(self):
        # Anonymous -> redirected (to login via the guarded dashboard chain).
        resp = self.client.get('/compliance/')
        self.assertIn(resp.status_code, (301, 302))

    def test_company_root_redirects(self):
        resp = self.client.get('/company/')
        self.assertIn(resp.status_code, (301, 302))

    def test_compliance_root_company_user_reaches_dashboard(self):
        self.client.force_login(_user('rr_co@x.com', company=_company('9911220004', 'r@x.com')))
        resp = self.client.get('/compliance/', follow=True)
        self.assertEqual(resp.status_code, 200)
