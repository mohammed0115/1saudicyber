"""R0: the full official catalogue (417 controls, 7 frameworks) imports cleanly.

Verifies the headline claim in the management doc: the shipped datasets total exactly 417
and the one-shot importer loads them idempotently.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from compliance.models import Control
from compliance.management.commands.import_all_official_controls import (
    OFFICIAL_FRAMEWORK_VERSIONS, EXPECTED_TOTAL)

PER_FRAMEWORK = {
    'NCA-ECC-2-2024': 108,
    'NCA-CCC-2-2024': 55,
    'NCA-CSCC-1-2019': 32,
    'NCA-OSMACC-1-2021': 15,
    'NCA-TCC-1-2021': 21,
    'ARAMCO-SACS-002': 92,
    'SABIC-CYBERTRUST-1-0': 94,
}


class OfficialCatalogueImportTests(TestCase):
    def test_imports_exactly_417_across_seven_frameworks(self):
        call_command('import_all_official_controls', apply=True, stdout=StringIO())
        total = Control.objects.filter(
            framework_version__code__in=OFFICIAL_FRAMEWORK_VERSIONS).count()
        self.assertEqual(total, EXPECTED_TOTAL)          # 417
        self.assertEqual(sum(PER_FRAMEWORK.values()), 417)
        for code, expected in PER_FRAMEWORK.items():
            got = Control.objects.filter(framework_version__code=code).count()
            self.assertEqual(got, expected, f'{code}: expected {expected}, got {got}')

    def test_import_is_idempotent(self):
        call_command('import_all_official_controls', apply=True, stdout=StringIO())
        first = Control.objects.filter(
            framework_version__code__in=OFFICIAL_FRAMEWORK_VERSIONS).count()
        call_command('import_all_official_controls', apply=True, stdout=StringIO())  # again
        second = Control.objects.filter(
            framework_version__code__in=OFFICIAL_FRAMEWORK_VERSIONS).count()
        self.assertEqual(first, second)                  # no duplication
        self.assertEqual(second, EXPECTED_TOTAL)
