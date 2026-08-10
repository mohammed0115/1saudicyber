"""P0-02 — Company deletion integrity: no application/admin path may cascade an issued
AuditReport away by deleting its company.
"""
from django.test import TestCase
from django.urls import reverse

from core.models import Company, User, CompanyDeletionProtected
from compliance.models import Assessment
from auditor_portal.models import AuditReport


def _company(cr):
    return Company.objects.create(name='C', cr_number=cr, sector='technology', size='small',
                                  contact_email=f'{cr}@x.com')


def _reported_company(cr, email):
    """A company that owns a completed assessment + an issued (write-once) report."""
    c = _company(cr)
    u = User.objects.create_user(email=email, password='longenough12')
    a = Assessment.objects.create(company=c, assessment_type='formal_audit', status='completed')
    AuditReport.objects.create(assessment=a, auditor=u, verdict='pass', executive_summary='s')
    return c, a


class CompanyDeletionProtectionTests(TestCase):
    # ---- model-level backstop (security) ----
    def test_instance_delete_refused(self):
        c, a = _reported_company('1111111111', 'r1@x.com')
        with self.assertRaises(CompanyDeletionProtected):
            c.delete()
        self.assertTrue(Company.objects.filter(pk=c.pk).exists())
        self.assertTrue(AuditReport.objects.filter(assessment=a).exists())

    def test_queryset_delete_refused(self):
        c, a = _reported_company('2222222222', 'r2@x.com')
        with self.assertRaises(CompanyDeletionProtected):
            Company.objects.filter(pk=c.pk).delete()
        self.assertTrue(Company.objects.filter(pk=c.pk).exists())
        self.assertTrue(AuditReport.objects.filter(assessment=a).exists())

    def test_bulk_delete_refused_if_any_member_protected(self):
        c1, a1 = _reported_company('3333333333', 'r3@x.com')
        c2 = _company('4444444444')                      # no report
        with self.assertRaises(CompanyDeletionProtected):
            Company.objects.filter(pk__in=[c1.pk, c2.pk]).delete()
        self.assertTrue(Company.objects.filter(pk=c1.pk).exists())
        self.assertTrue(Company.objects.filter(pk=c2.pk).exists())   # neither removed

    def test_cascade_cannot_be_used_to_reissue(self):
        c, a = _reported_company('1212121212', 'r12@x.com')
        original = AuditReport.objects.get(assessment=a)
        with self.assertRaises(CompanyDeletionProtected):
            Company.objects.filter(pk=c.pk).delete()
        self.assertTrue(AuditReport.objects.filter(pk=original.pk).exists())   # same report intact

    # ---- companies WITHOUT final records remain deletable per current policy ----
    def test_company_without_report_can_be_deleted(self):
        c = _company('5555555555')
        c.delete()
        self.assertFalse(Company.objects.filter(pk=c.pk).exists())

    def test_incomplete_assessment_company_can_be_deleted(self):
        c = _company('6666666666')
        Assessment.objects.create(company=c, assessment_type='formal_audit', status='auditor_review')
        c.delete()                                       # no issued report -> allowed
        self.assertFalse(Company.objects.filter(pk=c.pk).exists())

    def test_guard_does_not_block_reads(self):
        c, a = _reported_company('1313131313', 'r13@x.com')
        self.assertEqual(Company.objects.filter(pk=c.pk).count(), 1)   # read still works
        self.assertEqual(Company.objects.get(pk=c.pk), c)

    # ---- application view (PDPL self-service delete) ----
    def test_pdpl_self_delete_refused_when_reports_exist(self):
        c, a = _reported_company('7777777777', 'r7@x.com')
        admin_user = User.objects.create_user(email='cadm7@x.com', password='longenough12',
                                              company=c, role='company_admin')
        self.client.force_login(admin_user)
        resp = self.client.post(reverse('core:delete_company_data'), {'confirm': 'DELETE'})
        self.assertEqual(resp.status_code, 200)          # re-rendered with error, not deleted
        self.assertTrue(Company.objects.filter(pk=c.pk).exists())
        self.assertTrue(AuditReport.objects.filter(assessment=a).exists())

    # ---- Django admin ----
    def test_admin_single_delete_refused(self):
        c, a = _reported_company('8888888888', 'r8@x.com')
        su = User.objects.create_superuser(email='su8@x.com', password='longenough12')
        self.client.force_login(su)
        resp = self.client.post(reverse('admin:core_company_delete', args=[c.pk]), {'post': 'yes'})
        self.assertIn(resp.status_code, (403, 302))
        self.assertTrue(Company.objects.filter(pk=c.pk).exists())    # not deleted

    def test_admin_bulk_delete_refused(self):
        c, a = _reported_company('9999999999', 'r9@x.com')
        su = User.objects.create_superuser(email='su9@x.com', password='longenough12')
        self.client.force_login(su)
        self.client.post(reverse('admin:core_company_changelist'), {
            'action': 'delete_selected', '_selected_action': [str(c.pk)], 'post': 'yes'})
        self.assertTrue(Company.objects.filter(pk=c.pk).exists())    # survives
        self.assertTrue(AuditReport.objects.filter(assessment=a).exists())
