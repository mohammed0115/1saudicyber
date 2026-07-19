"""Auditor Portal — access guard, Assessment wiring, tenant scoping, no-certificate."""
from django.test import TestCase
from django.urls import reverse

from core.models import User, Company
from compliance.models import CompanyControl, Assessment
from compliance.tests import _company_with_control, _assigned_auditor_user, _journey_user
from auditor_portal.models import AuditorNote, AuditReport
from monitoring.models import CertificateTracker


def _company_control(company, control):
    return CompanyControl.objects.get_or_create(company=company, control=control)[0]


class AuditorPortalGuardTests(TestCase):
    def test_active_assigned_auditor_can_open_dashboard(self):
        c, control = _company_with_control()
        aud = _assigned_auditor_user(c, email='apt_ok@x.com')
        self.client.force_login(aud)
        self.assertEqual(self.client.get(reverse('auditor_portal:dashboard')).status_code, 200)

    def test_inactive_auditor_denied(self):
        c, control = _company_with_control()
        from auditors.models import AuditorProfile
        u = User.objects.create_user(email='apt_pending@x.com', password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=u, full_name='Pend', status='pending_review')  # not active
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('auditor_portal:dashboard')).status_code, 302)

    def test_company_user_denied(self):
        c, control = _company_with_control()
        self.client.force_login(_journey_user(c, email='apt_co@x.com'))
        self.assertEqual(self.client.get(reverse('auditor_portal:dashboard')).status_code, 302)


class AuditorPortalWiringTests(TestCase):
    def test_dashboard_creates_assessment_from_accepted_assignment(self):
        c, control = _company_with_control()
        aud = _assigned_auditor_user(c, email='apt_wire@x.com')
        self.assertEqual(Assessment.objects.filter(company=c, assigned_auditor=aud).count(), 0)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        self.assertEqual(Assessment.objects.filter(company=c, assigned_auditor=aud).count(), 1)

    def test_dashboard_is_idempotent(self):
        c, control = _company_with_control()
        aud = _assigned_auditor_user(c, email='apt_idem@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        self.client.get(reverse('auditor_portal:dashboard'))
        self.assertEqual(Assessment.objects.filter(company=c, assigned_auditor=aud).count(), 1)


class AuditorPortalTenantTests(TestCase):
    def _assessment_for(self, auditor):
        self.client.force_login(auditor)
        self.client.get(reverse('auditor_portal:dashboard'))
        return Assessment.objects.get(assigned_auditor=auditor)

    def test_auditor_cannot_open_another_auditors_assessment(self):
        cA, ctlA = _company_with_control()
        audA = _assigned_auditor_user(cA, email='apt_a@x.com')
        aA = self._assessment_for(audA)
        cB = Company.objects.create(name='B', cr_number='2020202020', sector='technology',
                                    size='small', contact_email='b@x.com')
        audB = _assigned_auditor_user(cB, email='apt_b@x.com')
        self.client.force_login(audB)
        self.assertEqual(self.client.get(
            reverse('auditor_portal:review_assessment', args=[aA.id])).status_code, 404)

    def test_add_note_rejects_cross_tenant_control(self):
        cA, ctlA = _company_with_control()
        audA = _assigned_auditor_user(cA, email='apt_note@x.com')
        aA = self._assessment_for(audA)
        cB = Company.objects.create(name='B2', cr_number='3030303030', sector='technology',
                                    size='small', contact_email='b2@x.com')
        ccB = _company_control(cB, ctlA)          # a control that belongs to a DIFFERENT company
        self.client.force_login(audA)
        resp = self.client.post(reverse('auditor_portal:add_note', args=[aA.id, ccB.id]), {'note': 'x'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(AuditorNote.objects.count(), 0)

    def test_add_note_own_control_succeeds(self):
        cA, ctlA = _company_with_control()
        audA = _assigned_auditor_user(cA, email='apt_note2@x.com')
        aA = self._assessment_for(audA)
        ccA = _company_control(cA, ctlA)
        self.client.force_login(audA)
        self.client.post(reverse('auditor_portal:add_note', args=[aA.id, ccA.id]), {'note': 'ok'})
        self.assertEqual(AuditorNote.objects.filter(assessment=aA, company_control=ccA).count(), 1)


class AuditorPortalNoCertificateTests(TestCase):
    def test_submit_report_does_not_issue_certificate_or_certify(self):
        c, control = _company_with_control()
        aud = _assigned_auditor_user(c, email='apt_cert@x.com')
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                         {'verdict': 'pass', 'executive_summary': 'internal review'})
        a.refresh_from_db(); c.refresh_from_db()
        self.assertTrue(AuditReport.objects.filter(assessment=a).exists())
        self.assertEqual(a.status, 'completed')
        # Internal review must NEVER issue a certificate or mark the company certified.
        self.assertEqual(CertificateTracker.objects.filter(company=c).count(), 0)
        self.assertNotEqual(c.status, 'certified')


class AuditorPortalRequirePostTests(TestCase):
    """F-AUDIT: mutation views reject GET (405), matching save_verdict/RFI parity."""

    def _assessment_for(self, c, email):
        aud = _assigned_auditor_user(c, email=email)
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        return aud, Assessment.objects.get(assigned_auditor=aud)

    def test_add_note_get_is_405(self):
        c, ctl = _company_with_control()
        aud, a = self._assessment_for(c, 'apt_rp_note@x.com')
        cc = _company_control(c, ctl)
        resp = self.client.get(reverse('auditor_portal:add_note', args=[a.id, cc.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(AuditorNote.objects.count(), 0)

    def test_submit_report_get_is_405(self):
        c, ctl = _company_with_control()
        aud, a = self._assessment_for(c, 'apt_rp_rep@x.com')
        resp = self.client.get(reverse('auditor_portal:submit_report', args=[a.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertFalse(AuditReport.objects.filter(assessment=a).exists())


class AuditorPortalWorkspaceArabicTests(TestCase):
    """UAT-AUDITOR-PORTAL-REVIEW-WORKSPACE-ARABIC-RTL-B — Arabic/RTL review workspace,
    safe advisory-only wording, reason-required document requests, access control."""

    def _assessment_for(self, auditor):
        self.client.force_login(auditor)
        self.client.get(reverse('auditor_portal:dashboard'))
        return Assessment.objects.get(assigned_auditor=auditor)

    _FORBIDDEN = ('شهادة NCA', 'اعتماد NCA', 'شهادة Aramco', 'شهادة SABIC',
                  'Official certificate', 'Certified by')

    # ---- review_assessment: Arabic, stepper, disclaimer, no cert wording ----
    def test_review_assessment_is_arabic(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_ra@x.com')
        a = self._assessment_for(aud)
        body = self.client.get(reverse('auditor_portal:review_assessment', args=[a.id])).content.decode()
        self.assertIn('مراجعة الضوابط', body)
        self.assertIn('مسار مراجعة المدقق', body)          # workspace stepper
        self.assertIn('لا تمثل شهادة امتثال رسمية', body)  # safe disclaimer
        self.assertIn('إصدار تقرير مراجعة داخلي', body)
        for en in ('Controls Review', 'Company Information', 'Submit Final Report', 'Not Started'):
            self.assertNotIn(en, body)
        for bad in self._FORBIDDEN:
            self.assertNotIn(bad, body)

    # ---- review_control: Arabic, advisory disclaimer, read-only evidence ----
    def test_review_control_is_arabic(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_rc@x.com')
        a = self._assessment_for(aud)
        cc = _company_control(c, ctl)
        body = self.client.get(
            reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertIn('التحليل الاستشاري', body)
        self.assertIn('التحليل الاستشاري يساعد المدقق ولا يمثل قراراً نهائياً', body)
        self.assertIn('إضافة ملاحظة مدقق', body)
        self.assertIn('طلب استكمال من الشركة', body)
        self.assertIn('لا يمكن للمدقق حذف أو استبدال أدلة الشركة', body)
        for en in ('Control Information', 'Uploaded Evidence', 'Add Note', 'Request Document', 'AI Verdict'):
            self.assertNotIn(en, body)
        for bad in self._FORBIDDEN:
            self.assertNotIn(bad, body)

    # ---- access control ----
    def test_pending_auditor_cannot_open_review_assessment(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_act@x.com')
        a = self._assessment_for(aud)
        from auditors.models import AuditorProfile
        pending = User.objects.create_user(email='wsb_pend@x.com', password='longenough12', role='auditor')
        AuditorProfile.objects.create(user=pending, full_name='P', status='pending_review')
        self.client.force_login(pending)
        self.assertIn(self.client.get(
            reverse('auditor_portal:review_assessment', args=[a.id])).status_code, (302, 403, 404))

    def test_company_user_cannot_open_review_assessment(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_ca_a@x.com')
        a = self._assessment_for(aud)
        self.client.force_login(_journey_user(c, email='wsb_ca@x.com'))
        self.assertIn(self.client.get(
            reverse('auditor_portal:review_assessment', args=[a.id])).status_code, (302, 403, 404))

    # ---- document request: reason required ----
    def test_request_document_requires_reason(self):
        from auditor_portal.models import DocumentRequest
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_dr@x.com')
        a = self._assessment_for(aud)
        cc = _company_control(c, ctl)
        self.client.force_login(aud)
        # missing title/reason -> no RFI created
        self.client.post(reverse('auditor_portal:request_document', args=[a.id, cc.id]),
                         {'title': '', 'description': '', 'description_ar': ''})
        self.assertEqual(DocumentRequest.objects.count(), 0)
        # title + reason -> RFI created
        self.client.post(reverse('auditor_portal:request_document', args=[a.id, cc.id]),
                         {'title': 'سياسة كلمات المرور', 'description_ar': 'يرجى رفع سياسة كلمات المرور'})
        self.assertEqual(DocumentRequest.objects.filter(assessment=a, company_control=cc).count(), 1)

    # ---- arabic flash messages, no certificate wording ----
    def test_submit_report_arabic_message(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_sr@x.com')
        a = self._assessment_for(aud)
        self.client.force_login(aud)
        resp = self.client.post(reverse('auditor_portal:submit_report', args=[a.id]),
                                {'verdict': 'pass'}, follow=True)
        body = resp.content.decode()
        self.assertIn('تقرير المراجعة الداخلي', body)
        self.assertNotIn('official certification', body)

    def test_add_note_arabic_message(self):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='wsb_an@x.com')
        a = self._assessment_for(aud)
        cc = _company_control(c, ctl)
        self.client.force_login(aud)
        resp = self.client.post(reverse('auditor_portal:add_note', args=[a.id, cc.id]),
                                {'note': 'ملاحظة'}, follow=True)
        self.assertIn('تمت إضافة ملاحظة المدقق', resp.content.decode())


class AuditorPortalVerdictRfiTests(TestCase):
    """UAT-...-CONTROL-VERDICT-AND-RFI-LOOP-C — per-control internal verdicts + the
    RFI (request-for-information) loop between auditor and company."""

    def _assessment_for(self, auditor):
        self.client.force_login(auditor)
        self.client.get(reverse('auditor_portal:dashboard'))
        return Assessment.objects.get(assigned_auditor=auditor)

    def _setup(self, email='vr_aud@x.com'):
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email=email)
        a = self._assessment_for(aud)
        cc = _company_control(c, ctl)
        return c, ctl, aud, a, cc

    def _verdict_url(self, a, cc):
        return reverse('auditor_portal:save_verdict', args=[a.id, cc.id])

    def _rfi_url(self, a, cc):
        return reverse('auditor_portal:request_document', args=[a.id, cc.id])

    # ---------- verdict ----------
    def test_auditor_can_create_compliant_verdict(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, aud, a, cc = self._setup()
        self.client.force_login(aud)
        self.client.post(self._verdict_url(a, cc), {'status': 'compliant'})
        v = AuditorControlVerdict.objects.filter(assessment=a, company_control=cc).first()
        self.assertIsNotNone(v)
        self.assertEqual(v.status, 'compliant')

    def test_non_compliant_requires_rationale_and_recommendation(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, aud, a, cc = self._setup(email='vr_neg@x.com')
        self.client.force_login(aud)
        # missing rationale/recommendation -> not created
        self.client.post(self._verdict_url(a, cc), {'status': 'non_compliant'})
        self.assertEqual(AuditorControlVerdict.objects.count(), 0)
        # with both -> created
        self.client.post(self._verdict_url(a, cc),
                         {'status': 'non_compliant', 'rationale': 'لا توجد سياسة', 'recommendation': 'اعتماد سياسة'})
        self.assertEqual(AuditorControlVerdict.objects.filter(status='non_compliant').count(), 1)

    def test_needs_more_evidence_requires_rationale(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, aud, a, cc = self._setup(email='vr_nme@x.com')
        self.client.force_login(aud)
        self.client.post(self._verdict_url(a, cc), {'status': 'needs_more_evidence', 'recommendation': 'ارفع الدليل'})
        self.assertEqual(AuditorControlVerdict.objects.count(), 0)  # rationale missing

    def test_verdict_update_overwrites(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, aud, a, cc = self._setup(email='vr_upd@x.com')
        self.client.force_login(aud)
        self.client.post(self._verdict_url(a, cc), {'status': 'compliant'})
        self.client.post(self._verdict_url(a, cc),
                         {'status': 'partially_compliant', 'rationale': 'جزئي'})
        self.assertEqual(AuditorControlVerdict.objects.filter(assessment=a, company_control=cc).count(), 1)
        self.assertEqual(AuditorControlVerdict.objects.get(assessment=a, company_control=cc).status,
                         'partially_compliant')

    def test_other_auditor_cannot_create_verdict(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, audA, aA, ccA = self._setup(email='vr_a@x.com')
        cB = Company.objects.create(name='VB', cr_number='8181818181', sector='technology',
                                    size='small', contact_email='vb@x.com')
        audB = _assigned_auditor_user(cB, email='vr_b@x.com')
        self._assessment_for(audB)
        self.client.force_login(audB)
        self.assertEqual(self.client.post(self._verdict_url(aA, ccA), {'status': 'compliant'}).status_code, 404)
        self.assertEqual(AuditorControlVerdict.objects.count(), 0)

    def test_company_user_cannot_create_verdict(self):
        from auditor_portal.models import AuditorControlVerdict
        c, ctl, aud, a, cc = self._setup(email='vr_cu_a@x.com')
        self.client.force_login(_journey_user(c, email='vr_cu@x.com'))
        self.client.post(self._verdict_url(a, cc), {'status': 'compliant'})
        self.assertEqual(AuditorControlVerdict.objects.count(), 0)

    def test_verdict_get_does_not_mutate(self):
        c, ctl, aud, a, cc = self._setup(email='vr_get@x.com')
        self.client.force_login(aud)
        self.assertEqual(self.client.get(self._verdict_url(a, cc)).status_code, 405)

    def test_verdict_shows_on_review_control_and_counts_on_assessment(self):
        c, ctl, aud, a, cc = self._setup(email='vr_show@x.com')
        self.client.force_login(aud)
        self.client.post(self._verdict_url(a, cc), {'status': 'compliant'})
        rc = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertIn('الحكم الداخلي على الضابط', rc)
        self.assertIn('متوافق', rc)
        ra = self.client.get(reverse('auditor_portal:review_assessment', args=[a.id])).content.decode()
        self.assertIn('تغطية الأحكام الداخلية', ra)
        self.assertIn('جاهزية التقرير الداخلي', ra)

    # ---------- RFI ----------
    def test_auditor_creates_rfi_open(self):
        from auditor_portal.models import DocumentRequest
        c, ctl, aud, a, cc = self._setup(email='rfi_c@x.com')
        self.client.force_login(aud)
        self.client.post(self._rfi_url(a, cc), {'title': 'سياسة', 'description_ar': 'ارفع السياسة', 'priority': 'high'})
        r = DocumentRequest.objects.filter(assessment=a, company_control=cc).first()
        self.assertIsNotNone(r)
        self.assertEqual(r.status, 'open')
        self.assertEqual(r.priority, 'high')

    def test_company_sees_and_responds_to_rfi(self):
        from auditor_portal.models import DocumentRequest, CompanyRFIResponse
        c, ctl, aud, a, cc = self._setup(email='rfi_resp_a@x.com')
        self.client.force_login(aud)
        self.client.post(self._rfi_url(a, cc), {'title': 'سياسة كلمات المرور', 'description_ar': 'ارفعوا السياسة'})
        rfi = DocumentRequest.objects.get(assessment=a, company_control=cc)
        cu = _journey_user(c, email='rfi_cu@x.com')
        self.client.force_login(cu)
        body = self.client.get(reverse('auditor_portal:company_rfi_list')).content.decode()
        self.assertIn('طلبات المعلومات (RFI)', body)
        self.assertIn('سياسة كلمات المرور', body)
        self.client.post(reverse('auditor_portal:company_rfi_respond', args=[rfi.id]),
                         {'response_text': 'تم رفع السياسة'})
        rfi.refresh_from_db()
        self.assertEqual(rfi.status, 'responded')
        self.assertEqual(CompanyRFIResponse.objects.filter(request=rfi).count(), 1)

    def test_other_company_cannot_respond(self):
        from auditor_portal.models import DocumentRequest, CompanyRFIResponse
        c, ctl, aud, a, cc = self._setup(email='rfi_oc_a@x.com')
        self.client.force_login(aud)
        self.client.post(self._rfi_url(a, cc), {'title': 't', 'description_ar': 'x'})
        rfi = DocumentRequest.objects.get(assessment=a, company_control=cc)
        other = Company.objects.create(name='Other', cr_number='7777777777', sector='technology',
                                       size='small', contact_email='o@x.com')
        self.client.force_login(_journey_user(other, email='rfi_oc@x.com'))
        self.assertEqual(self.client.post(reverse('auditor_portal:company_rfi_respond', args=[rfi.id]),
                                          {'response_text': 'x'}).status_code, 404)
        self.assertEqual(CompanyRFIResponse.objects.count(), 0)

    def test_auditor_closes_rfi_requires_note(self):
        from auditor_portal.models import DocumentRequest
        c, ctl, aud, a, cc = self._setup(email='rfi_close@x.com')
        self.client.force_login(aud)
        self.client.post(self._rfi_url(a, cc), {'title': 't', 'description_ar': 'x'})
        rfi = DocumentRequest.objects.get(assessment=a, company_control=cc)
        self.client.post(reverse('auditor_portal:close_rfi', args=[rfi.id]), {'closing_note': ''})
        rfi.refresh_from_db(); self.assertNotEqual(rfi.status, 'closed')
        self.client.post(reverse('auditor_portal:close_rfi', args=[rfi.id]), {'closing_note': 'مكتمل'})
        rfi.refresh_from_db(); self.assertEqual(rfi.status, 'closed')

    def test_other_auditor_cannot_close_rfi(self):
        from auditor_portal.models import DocumentRequest
        c, ctl, audA, aA, ccA = self._setup(email='rfi_oa_a@x.com')
        self.client.force_login(audA)
        self.client.post(self._rfi_url(aA, ccA), {'title': 't', 'description_ar': 'x'})
        rfi = DocumentRequest.objects.get(assessment=aA, company_control=ccA)
        cB = Company.objects.create(name='RB', cr_number='8282828282', sector='technology',
                                    size='small', contact_email='rb@x.com')
        audB = _assigned_auditor_user(cB, email='rfi_oa_b@x.com')
        self._assessment_for(audB)
        self.client.force_login(audB)
        self.assertEqual(self.client.post(reverse('auditor_portal:close_rfi', args=[rfi.id]),
                                          {'closing_note': 'x'}).status_code, 404)

    def test_anonymous_redirected_from_company_rfi(self):
        resp = self.client.get(reverse('auditor_portal:company_rfi_list'))
        self.assertIn(resp.status_code, (302, 403))

    # ---------- report readiness ----------
    def test_open_rfi_blocks_report(self):
        from auditor_portal.models import DocumentRequest
        c, ctl, aud, a, cc = self._setup(email='rr_block@x.com')
        self.client.force_login(aud)
        self.client.post(self._rfi_url(a, cc), {'title': 't', 'description_ar': 'x'})  # open RFI
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db()
        self.assertNotEqual(a.status, 'completed')          # blocked while RFI open

    def test_closed_rfi_and_verdict_allow_report(self):
        from auditor_portal.models import DocumentRequest
        c, ctl, aud, a, cc = self._setup(email='rr_ok@x.com')
        self.client.force_login(aud)
        self.client.post(self._verdict_url(a, cc), {'status': 'compliant'})
        self.client.post(self._rfi_url(a, cc), {'title': 't', 'description_ar': 'x'})
        rfi = DocumentRequest.objects.get(assessment=a, company_control=cc)
        self.client.post(reverse('auditor_portal:close_rfi', args=[rfi.id]), {'closing_note': 'ok'})
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'completed')


class AuditorPortalE2ELoopTests(TestCase):
    """UAT-AUDITOR-PORTAL-E2E-QA-POLISH-D — full auditor↔company review loop end to end."""

    _FORBIDDEN = ('شهادة NCA', 'اعتماد NCA', 'شهادة Aramco', 'شهادة SABIC',
                  'Official certificate', 'Certified by')

    def test_full_rfi_and_verdict_loop(self):
        from auditor_portal.models import DocumentRequest, CompanyRFIResponse, AuditorControlVerdict
        c, ctl = _company_with_control()
        aud = _assigned_auditor_user(c, email='e2e_aud@x.com')
        cu = _journey_user(c, email='e2e_cu@x.com')

        # 1) auditor opens dashboard -> assessment materialised; workspace pages load
        self.client.force_login(aud)
        self.client.get(reverse('auditor_portal:dashboard'))
        a = Assessment.objects.get(assigned_auditor=aud)
        cc = _company_control(c, ctl)
        self.assertEqual(self.client.get(reverse('auditor_portal:review_assessment', args=[a.id])).status_code, 200)
        ra_body = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        for bad in self._FORBIDDEN:
            self.assertNotIn(bad, ra_body)

        # 2) auditor creates an RFI
        self.client.post(reverse('auditor_portal:request_document', args=[a.id, cc.id]),
                         {'title': 'سياسة كلمات المرور', 'description_ar': 'يرجى رفع السياسة', 'priority': 'high'})
        rfi = DocumentRequest.objects.get(assessment=a, company_control=cc)
        self.assertEqual(rfi.status, 'open')

        # 3) report is BLOCKED while the RFI is open
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db(); self.assertNotEqual(a.status, 'completed')

        # 4) company sees the RFI (dedicated page + dashboard banner) and responds
        self.client.force_login(cu)
        dash = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertIn(reverse('auditor_portal:company_rfi_list'), dash)     # banner link
        self.assertIn('طلب استكمال من المدقق', dash)
        rfi_page = self.client.get(reverse('auditor_portal:company_rfi_list')).content.decode()
        self.assertIn('سياسة كلمات المرور', rfi_page)
        self.client.post(reverse('auditor_portal:company_rfi_respond', args=[rfi.id]),
                         {'response_text': 'تم رفع السياسة المطلوبة'})
        rfi.refresh_from_db()
        self.assertEqual(rfi.status, 'responded')
        self.assertEqual(CompanyRFIResponse.objects.filter(request=rfi).count(), 1)

        # 5) a responded-but-not-closed RFI still counts as open -> report still blocked
        self.client.force_login(aud)
        rc = self.client.get(reverse('auditor_portal:review_control', args=[a.id, cc.id])).content.decode()
        self.assertIn('تم رفع السياسة المطلوبة', rc)                        # auditor sees the response
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db(); self.assertNotEqual(a.status, 'completed')

        # 6) auditor closes the RFI and records a verdict
        self.client.post(reverse('auditor_portal:close_rfi', args=[rfi.id]), {'closing_note': 'تمت المعالجة'})
        rfi.refresh_from_db(); self.assertEqual(rfi.status, 'closed')
        self.client.post(reverse('auditor_portal:save_verdict', args=[a.id, cc.id]), {'status': 'compliant'})
        self.assertTrue(AuditorControlVerdict.objects.filter(assessment=a, company_control=cc).exists())

        # 7) with no open RFI and a verdict recorded, the internal report can be issued
        self.client.post(reverse('auditor_portal:submit_report', args=[a.id]), {'verdict': 'pass'})
        a.refresh_from_db(); self.assertEqual(a.status, 'completed')

    def test_compliance_dashboard_has_no_rfi_banner_when_none(self):
        c, ctl = _company_with_control()
        self.client.force_login(_journey_user(c, email='e2e_norfi@x.com'))
        body = self.client.get(reverse('compliance:dashboard')).content.decode()
        self.assertNotIn('طلب استكمال من المدقق', body)   # banner only when open RFI exists

    def test_auditor_dashboard_links_to_review_workspace(self):
        from compliance.tests import _company_with_assessments
        c, _fv, _s = _company_with_assessments()
        from auditors import services
        u, ap = _auditor_active(c, 'e2e_link@x.com')
        a, _ = services.create_assignment(c, ap, requested_by=None)
        services.respond_to_assignment(a, 'accept', responder=u)
        self.client.force_login(u)
        body = self.client.get(reverse('auditors:dashboard')).content.decode()
        self.assertIn(reverse('auditor_portal:dashboard'), body)
        self.assertIn('مساحة مراجعة الأدلة', body)


def _auditor_active(company, email):
    """An active auditor profile (helper for the dashboard-link E2E test)."""
    from auditors.models import AuditorProfile
    u = User.objects.create_user(email=email, username=email, password='longenough12', role='auditor')
    p = AuditorProfile.objects.create(user=u, full_name='E2E Auditor', status='active', is_available=True)
    return u, p
