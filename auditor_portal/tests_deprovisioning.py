"""P0-03 — Auditor de-provisioning integrity.

When a platform admin suspends or rejects an auditor, every access path must fail closed
immediately and atomically:

  * the auditor's live assignments (requested/accepted) are revoked ('cancelled'),
  * the auditor-only login is disabled (user.is_active=False, terminating live sessions),
  * every server-side guard (portal, messaging, RFI attachments, evidence/verdict) re-checks
    a SINGLE eligibility policy from the DB on each request.

These tests split two concerns:
  (A) the GUARD is hardened — a suspended/rejected auditor whose login is still enabled reaches
      the view and is denied there (proves the guard, not just the login flag);
  (B) the admin TRANSACTION is atomic — status change + assignment revocation + login disable
      commit together or not at all.

Uses real models + views (not mock-only), except one targeted atomicity test that forces a
mid-transaction failure.
"""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import User
from auditors.models import AuditorProfile, AuditorAssignment
from auditors import services, admin_services
from auditors.tests import _auditor, _assignment
from compliance.models import Assessment
from compliance.tests import (_company_with_control, _company, _assigned_auditor_user,
                              _journey_user, _SUF)
from auditor_portal.tests import _company_control
from auditor_portal.models import DocumentRequest, CompanyRFIResponse, CompanyMessage


def _read(resp):
    return b''.join(resp.streaming_content)


def _staff(email='p0staff@x.com'):
    return User.objects.create_user(email=email, username=email, password='longenough12',
                                    role='admin', is_staff=True)


def _auditor_with_assignment(company, *, profile_status='active', assignment_status='accepted'):
    """An auditor + a (given) assignment to `company`. The USER stays is_active=True so
    force_login reaches the view — isolating the GUARD from the login-disable mechanism."""
    u, p = _auditor(status=profile_status)
    _assignment(company, p, status=assignment_status)
    return u, p


# ============================================================
# §11.1-8 — canonical eligibility policy (single source of truth)
# ============================================================
class CanonicalEligibilityPolicyTests(TestCase):
    def setUp(self):
        self.a, self.ctl = _company_with_control()
        self.b = _company(cr_number='8181818181')

    def test_active_profile_accepted_assignment_allowed(self):
        u, _ = _auditor_with_assignment(self.a)
        self.assertTrue(services.is_auditor_eligible_for_company(u, self.a))

    def test_suspended_profile_denied(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='suspended')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_rejected_inactive_profile_denied(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='inactive')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_pending_profile_denied(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='pending_review')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_inactive_user_denied_even_if_profile_active(self):
        u, _ = _auditor_with_assignment(self.a)
        u.is_active = False
        u.save(update_fields=['is_active'])
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_cancelled_assignment_denied(self):
        u, _ = _auditor_with_assignment(self.a, assignment_status='cancelled')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_requested_assignment_denied(self):
        u, _ = _auditor_with_assignment(self.a, assignment_status='requested')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_assignment_for_other_company_denied(self):
        u, _ = _auditor_with_assignment(self.a)   # accepted for A only
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.b))

    def test_no_profile_denied(self):
        u = User.objects.create_user(email='noprof@x.com', password='longenough12', role='auditor')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_no_assignment_denied(self):
        u, _ = _auditor(status='active')
        self.assertFalse(services.is_auditor_eligible_for_company(u, self.a))

    def test_anonymous_denied(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(services.is_auditor_eligible_for_company(AnonymousUser(), self.a))


# ============================================================
# §11.9-13 — messaging thread (read + post)
# ============================================================
class MessagingDeprovisioningTests(TestCase):
    def setUp(self):
        self.a, self.ctl = _company_with_control()

    def _thread_url(self, company):
        return reverse('auditor_portal:message_thread', args=[company.id])

    def _post_url(self, company):
        return reverse('auditor_portal:post_message', args=[company.id])

    def test_suspended_auditor_cannot_read_thread(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='suspended')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self._thread_url(self.a)).status_code, 404)

    def test_suspended_auditor_cannot_post_message(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='suspended')
        self.client.force_login(u)
        resp = self.client.post(self._post_url(self.a), {'body': 'محاولة بعد الإيقاف'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(CompanyMessage.objects.filter(company=self.a).count(), 0)

    def test_rejected_auditor_cannot_read_thread(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='inactive')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self._thread_url(self.a)).status_code, 404)

    def test_auditor_of_other_company_cannot_read_thread(self):
        b = _company(cr_number='7171717171')
        u, _ = _auditor_with_assignment(b)   # accepted for B, not A
        self.client.force_login(u)
        self.assertEqual(self.client.get(self._thread_url(self.a)).status_code, 404)

    def test_active_accepted_auditor_retains_thread_access(self):
        aud = _assigned_auditor_user(self.a, email='msg_live_aud@x.com')
        self.client.force_login(aud)
        self.assertEqual(self.client.get(self._thread_url(self.a)).status_code, 200)
        self.client.post(self._post_url(self.a), {'body': 'رسالة مدقّق نشط'})
        self.assertEqual(CompanyMessage.objects.filter(company=self.a).count(), 1)


# ============================================================
# §11.14-18 — RFI attachment downloads
# ============================================================
class RfiAttachmentDeprovisioningTests(TestCase):
    def setUp(self):
        self.a, self.ctl = _company_with_control()
        cc = _company_control(self.a, self.ctl)
        seed = _assigned_auditor_user(self.a, email='rfi_seed_aud@x.com')  # owns the RFI
        assessment = Assessment.objects.create(
            company=self.a, assigned_auditor=seed,
            assessment_type='formal_audit', status='auditor_review')
        dr = DocumentRequest.objects.create(assessment=assessment, company_control=cc,
                                            auditor=seed, description='need doc')
        self.rfi = CompanyRFIResponse.objects.create(
            request=dr, responder=_journey_user(self.a, email='rfi_resp@x.com'),
            response_text='here', attachment=_SUF('proof.pdf', b'%PDF-1.4 rfi-secret'))
        self.url = reverse('auditor_portal:download_rfi_attachment', args=[self.rfi.id])

    def test_suspended_auditor_cannot_download(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='suspended')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_rejected_auditor_cannot_download(self):
        u, _ = _auditor_with_assignment(self.a, profile_status='inactive')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_cancelled_assignment_cannot_download(self):
        u, _ = _auditor_with_assignment(self.a, assignment_status='cancelled')
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_auditor_of_other_company_cannot_download(self):
        b = _company(cr_number='6262626262')
        u, _ = _auditor_with_assignment(b)   # accepted for B, not A
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_active_accepted_auditor_can_download(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_read(resp), b'%PDF-1.4 rfi-secret')


# ============================================================
# §11.19-26 — suspend/reject transaction
# ============================================================
class SuspendRejectTransactionTests(TestCase):
    def setUp(self):
        self.admin = _staff()
        self.a, self.ctl = _company_with_control()

    def _active_auditor(self, email_status='active'):
        u, p = _auditor(status='active')
        return u, p

    def test_suspend_revokes_accepted_assignment_and_disables_login(self):
        u, p = _auditor(status='active')
        asg = _assignment(self.a, p, status='accepted')
        admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='مخالفة')
        p.refresh_from_db(); asg.refresh_from_db(); u.refresh_from_db()
        self.assertEqual(p.status, 'suspended')
        self.assertEqual(asg.status, 'cancelled')          # live assignment revoked
        self.assertFalse(u.is_active)                       # login disabled
        # audit log records the revocation for forensics
        from core.models import AuditLog
        log = AuditLog.objects.filter(action='auditor_suspend').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('revoked_assignment_count'), 1)
        self.assertIn(asg.id, log.metadata.get('revoked_assignment_ids'))
        self.assertTrue(log.metadata.get('user_login_disabled'))

    def test_reject_revokes_accepted_and_pending_assignments(self):
        u, p = _auditor(status='active')
        a2 = _company(cr_number='5252525252')
        accepted = _assignment(self.a, p, status='accepted')
        requested = _assignment(a2, p, status='requested')
        admin_services.apply_auditor_action(p, 'reject', self.admin, reason='بيانات ناقصة')
        accepted.refresh_from_db(); requested.refresh_from_db(); p.refresh_from_db()
        self.assertEqual(p.status, 'inactive')
        self.assertEqual(accepted.status, 'cancelled')
        self.assertEqual(requested.status, 'cancelled')     # pending revoked too

    def test_suspend_is_atomic_on_assignment_failure(self):
        u, p = _auditor(status='active')
        asg = _assignment(self.a, p, status='accepted')
        # Force the assignment revocation to fail mid-transaction -> everything rolls back.
        with patch.object(AuditorAssignment, 'save', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='x')
        p.refresh_from_db(); asg.refresh_from_db(); u.refresh_from_db()
        self.assertEqual(p.status, 'active')                # profile change rolled back
        self.assertEqual(asg.status, 'accepted')            # assignment untouched
        self.assertTrue(u.is_active)                        # login untouched

    def test_repeat_suspend_is_rejected_no_conflicting_state(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='x')
        with self.assertRaises(admin_services.AuditorAdminError):
            admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='again')
        p.refresh_from_db()
        self.assertEqual(p.status, 'suspended')

    def test_assignment_history_is_preserved_not_deleted(self):
        u, p = _auditor(status='active')
        asg = _assignment(self.a, p, status='accepted')
        admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='x')
        asg.refresh_from_db()
        self.assertTrue(AuditorAssignment.objects.filter(pk=asg.pk).exists())  # row kept
        self.assertEqual(asg.status, 'cancelled')
        self.assertIsNotNone(asg.responded_at)
        self.assertEqual(asg.responded_by, self.admin)

    def test_reactivate_restores_login_but_not_assignments(self):
        u, p = _auditor(status='active')
        asg = _assignment(self.a, p, status='accepted')
        admin_services.apply_auditor_action(p, 'suspend', self.admin, reason='x')
        admin_services.apply_auditor_action(p, 'reactivate', self.admin)
        p.refresh_from_db(); asg.refresh_from_db(); u.refresh_from_db()
        self.assertEqual(p.status, 'active')
        self.assertTrue(u.is_active)                        # login restored
        self.assertEqual(asg.status, 'cancelled')           # assignment NOT auto-restored

    def test_suspended_auditor_cannot_accept_pending_assignment(self):
        # A suspended profile with a lingering 'requested' assignment cannot accept it.
        u, p = _auditor(status='suspended')
        asg = _assignment(self.a, p, status='requested')
        ok, err = services.respond_to_assignment(asg, 'accept', responder=u)
        self.assertFalse(ok)
        asg.refresh_from_db()
        self.assertEqual(asg.status, 'requested')           # not accepted

    def test_non_admin_cannot_apply_action(self):
        u, p = _auditor(status='active')
        company_user = _journey_user(self.a, email='cu_noadmin@x.com')
        with self.assertRaises(admin_services.AuditorAdminError):
            admin_services.apply_auditor_action(p, 'suspend', company_user, reason='x')
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')                # unchanged


# ============================================================
# §11.27-30 — regression (P0-01 / normal users unaffected)
# ============================================================
class DeprovisioningRegressionTests(TestCase):
    def setUp(self):
        self.a, self.ctl = _company_with_control()
        cc = _company_control(self.a, self.ctl)
        seed = _assigned_auditor_user(self.a, email='reg_seed_aud@x.com')
        assessment = Assessment.objects.create(
            company=self.a, assigned_auditor=seed,
            assessment_type='formal_audit', status='auditor_review')
        dr = DocumentRequest.objects.create(assessment=assessment, company_control=cc,
                                            auditor=seed, description='need doc')
        self.rfi = CompanyRFIResponse.objects.create(
            request=dr, responder=_journey_user(self.a, email='reg_resp@x.com'),
            response_text='here', attachment=_SUF('proof.pdf', b'%PDF-1.4 keep-working'))
        self.url = reverse('auditor_portal:download_rfi_attachment', args=[self.rfi.id])

    def test_active_accepted_auditor_still_downloads_rfi(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        self.client.force_login(u)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_read(resp), b'%PDF-1.4 keep-working')

    def test_owner_company_user_still_downloads_rfi(self):
        self.client.force_login(_journey_user(self.a, email='reg_owner@x.com'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_staff_still_downloads_rfi(self):
        self.client.force_login(_staff(email='reg_staff@x.com'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_reactivated_auditor_with_new_assignment_regains_access(self):
        u, p = _auditor(status='active')
        _assignment(self.a, p, status='accepted')
        admin_services.apply_auditor_action(p, 'suspend', _staff(email='reg_admin@x.com'), reason='x')
        admin_services.apply_auditor_action(p, 'reactivate', _staff(email='reg_admin2@x.com'))
        # explicit re-assignment (reactivation alone does not restore access)
        _assignment(self.a, p, status='accepted')
        u.refresh_from_db()
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url).status_code, 200)
