"""R2: per-control conditional applicability (cloud/OT/etc.) — narrows, never under-scopes."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Company
from compliance.models import (Framework, Domain, Control, FrameworkVersion,
                               ControlApplicabilityTag, CompanyIntakeProfile)
from compliance.applicability_engine import _refine_for_control, APPLICABLE, NOT_APPLICABLE


def _control(title='Cybersecurity requirements for cloud computing and hosting services',
             control_id='4-2-1'):
    fw, _ = Framework.objects.get_or_create(code='NCA_ECC', defaults={'name': 'ECC'})
    fv, _ = FrameworkVersion.objects.get_or_create(
        code='NCA-ECC-2-2024', defaults={'framework': fw, 'version_label': 'ECC 2:2024'})
    dom, _ = Domain.objects.get_or_create(framework=fw, name='Third Party and Cloud', defaults={'code': 'D4'})
    return Control.objects.create(framework=fw, framework_version=fv, control_id=control_id,
                                  title=title, description='x', domain=dom)


class ConditionalApplicabilityTests(TestCase):
    def setUp(self):
        self.control = _control()
        ControlApplicabilityTag.objects.create(control=self.control, tag='cloud', source='inferred')
        self.company = Company.objects.create(name='NoCloudCo', cr_number='7070707070',
                                              sector='technology', size='small', contact_email='n@x.com')

    def test_company_without_cloud_narrows_cloud_control(self):
        CompanyIntakeProfile.objects.create(company=self.company, uses_cloud_services=False,
                                            provides_cloud_services=False)
        status, reason = _refine_for_control(APPLICABLE, self.company, self.control)
        self.assertEqual(status, NOT_APPLICABLE)
        self.assertIn('cloud', reason)

    def test_company_with_cloud_keeps_cloud_control(self):
        CompanyIntakeProfile.objects.create(company=self.company, uses_cloud_services=True)
        status, _ = _refine_for_control(APPLICABLE, self.company, self.control)
        self.assertEqual(status, APPLICABLE)

    def test_no_intake_profile_never_narrows(self):
        # Conservative: without intake data we must NOT under-scope.
        status, _ = _refine_for_control(APPLICABLE, self.company, self.control)
        self.assertEqual(status, APPLICABLE)

    def test_untagged_control_always_applicable(self):
        CompanyIntakeProfile.objects.create(company=self.company, uses_cloud_services=False)
        plain = _control(title='Cybersecurity roles and responsibilities', control_id='1-1-1')
        status, _ = _refine_for_control(APPLICABLE, self.company, plain)
        self.assertEqual(status, APPLICABLE)


class TagConditionalControlsCommandTests(TestCase):
    def test_command_tags_cloud_titled_control(self):
        c = _control()  # title mentions cloud + hosting
        call_command('tag_conditional_controls', apply=True, stdout=StringIO())
        self.assertTrue(c.applicability_tags.filter(tag='cloud').exists())

    def test_command_is_idempotent(self):
        _control()
        call_command('tag_conditional_controls', apply=True, stdout=StringIO())
        before = ControlApplicabilityTag.objects.count()
        call_command('tag_conditional_controls', apply=True, stdout=StringIO())
        self.assertEqual(ControlApplicabilityTag.objects.count(), before)
