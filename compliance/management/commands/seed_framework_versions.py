"""
Phase 1 — seed the Source Registry + Framework Versioning layer.

Idempotent: uses get_or_create / update_or_create, never deletes anything, and
does NOT touch Control, CompanyControl, or Evidence. It does NOT import any
controls (that is Phase 2). It only registers official source documents and the
framework versions the platform must later distinguish between.

Usage:
    python manage.py seed_framework_versions
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from compliance.models import Framework, SourceDocument, FrameworkVersion


# Frameworks that must exist (created on demand, never overwritten destructively).
# key -> (code, name) ; existing rows are matched by code first, then by name.
FRAMEWORKS = {
    'NCA': ('NCA_ECC', 'NCA Essential Cybersecurity Controls'),
    'ARAMCO': ('ARAMCO_SACS002', 'Saudi Aramco SACS-002'),
    'SABIC': ('SABIC_CT', 'SABIC CyberTrust'),
    'LEGACY': ('LEGACY_BOOTSTRAP', 'Legacy Bootstrap (Consolidated Excel)'),
}

# Official / legacy source documents to register.
# (key, dict of fields). local_path is relative to the repo Docs/ tree where known.
SOURCE_DOCUMENTS = [
    ('NCA_ECC_2024', dict(
        title='NCA Essential Cybersecurity Controls (ECC) 2:2024', issuer='NCA',
        document_type='standard', version='2:2024', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/ECC--2024-EN.pdf')),
    ('NCA_CCC_2024', dict(
        title='NCA Cloud Cybersecurity Controls (CCC) 2:2024', issuer='NCA',
        document_type='standard', version='2:2024', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/CCC-2-2024-EN-.pdf')),
    ('NCA_CSCC', dict(
        title='NCA Critical Systems Cybersecurity Controls (CSCC)', issuer='NCA',
        document_type='standard', version='1:2019', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/Critical-Systems-Cybersecurity-Controls.pdf')),
    ('NCA_OTCC', dict(
        title='NCA Operational Technology Cybersecurity Controls (OTCC)', issuer='NCA',
        document_type='standard', version='1:2022', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/otcc_en.pdf')),
    ('NCA_DCC', dict(
        title='NCA Data Cybersecurity Controls (DCC)', issuer='NCA',
        document_type='standard', version='1:2022', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/Data-Cybersecurity-Controls-.pdf')),
    ('NCA_TCC', dict(
        title='NCA Telework Cybersecurity Controls (TCC)', issuer='NCA',
        document_type='standard', version='1:2021', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/telework_cybersecurity_controls-en.pdf')),
    ('NCA_OSMACC', dict(
        title='NCA Organizations Social Media Accounts Cybersecurity Controls (OSMACC)', issuer='NCA',
        document_type='standard', version='1:2021', language='en', status='active',
        is_current=True, local_path='Docs/SRS/NCA/osmacc-en.pdf')),
    ('ARAMCO_SACS002', dict(
        title='Saudi Aramco SACS-002 Third Party Cybersecurity Standard', issuer='ARAMCO',
        document_type='standard', version='SACS-002', language='en', status='active',
        is_current=True, local_path='Docs/SRS/ARAMCO/sacs-002-third-party-cybersecurity-standard.pdf')),
    ('SABIC_STD', dict(
        title='SABIC CyberTrust Standard', issuer='SABIC',
        document_type='standard', version='1.0', language='en', status='active',
        is_current=True, local_path='Docs/SRS/SABIC/SABIC CyberTrust Standard v1-0.pdf')),
    ('SABIC_GUIDE', dict(
        title='SABIC CyberTrust Guidelines', issuer='SABIC',
        document_type='guideline', version='1.0', language='en', status='active',
        is_current=True, local_path='Docs/SRS/SABIC/SABIC CyberTrust Guidelines v1-0.pdf')),
    ('SABIC_MANUAL', dict(
        title='SABIC CyberTrust Supplier Manual', issuer='SABIC',
        document_type='guideline', version='1.1', language='en', status='active',
        is_current=True, local_path='Docs/SRS/SABIC/SABIC CyberTrust Supplier Manual v1-1 (Public).pdf')),
    ('SABIC_REPORT', dict(
        title='SABIC CyberTrust Report Template', issuer='SABIC',
        document_type='template', version='1.0', language='en', status='active',
        is_current=True, local_path='Docs/SRS/SABIC/SABIC CyberTrust Report Template v1-0.docx')),
    ('LEGACY_334', dict(
        title='Consolidated Compliance Rules (334 controls)', issuer='LEGACY',
        document_type='bootstrap_excel', version='v2', language='bilingual', status='legacy',
        is_current=False, local_path='compliance/data/CyberTrust_KSA_Consolidated_Compliance_Rules_v2.xlsx',
        notes='Bootstrap/comparison only — NOT a governing source of truth.')),
]

# Framework versions to register.
# (code, framework_key, version_label, source_doc_key, status, is_default)
FRAMEWORK_VERSIONS = [
    ('NCA-ECC-2-2024', 'NCA', 'ECC 2:2024', 'NCA_ECC_2024', 'active', True),
    ('NCA-ECC-2018', 'NCA', 'ECC 1:2018', None, 'superseded', False),
    ('NCA-CCC-2-2024', 'NCA', 'CCC 2:2024', 'NCA_CCC_2024', 'active', False),
    ('NCA-CSCC-1-2019', 'NCA', 'CSCC 1:2019', 'NCA_CSCC', 'active', False),
    ('NCA-OTCC-1-2022', 'NCA', 'OTCC 1:2022', 'NCA_OTCC', 'active', False),
    ('NCA-DCC-1-2022', 'NCA', 'DCC', 'NCA_DCC', 'active', False),
    ('NCA-TCC-1-2021', 'NCA', 'TCC', 'NCA_TCC', 'active', False),
    ('NCA-OSMACC-1-2021', 'NCA', 'OSMACC', 'NCA_OSMACC', 'active', False),
    ('ARAMCO-SACS-002', 'ARAMCO', 'SACS-002', 'ARAMCO_SACS002', 'active', True),
    ('SABIC-CYBERTRUST-1-0', 'SABIC', 'CyberTrust v1.0', 'SABIC_STD', 'active', True),
    ('LEGACY-334-CONTROLS', 'LEGACY', 'Consolidated 334 (bootstrap)', 'LEGACY_334', 'legacy', False),
]


class Command(BaseCommand):
    help = 'Phase 1: seed Source Registry + Framework Versioning (idempotent, additive, no control import).'

    @transaction.atomic
    def handle(self, *args, **options):
        stats = {'src_created': 0, 'src_updated': 0, 'fw_created': 0, 'ver_created': 0, 'ver_updated': 0}

        # 1) Frameworks (match existing by code or name; create only if missing).
        frameworks = {}
        for key, (code, name) in FRAMEWORKS.items():
            fw = Framework.objects.filter(code=code).first() or Framework.objects.filter(name=name).first()
            if fw is None:
                fw = Framework.objects.create(code=code, name=name)
                stats['fw_created'] += 1
            frameworks[key] = fw

        # 2) Source documents.
        sources = {}
        for key, fields in SOURCE_DOCUMENTS:
            obj, created = SourceDocument.objects.update_or_create(
                title=fields['title'], issuer=fields['issuer'], defaults=fields)
            sources[key] = obj
            stats['src_created' if created else 'src_updated'] += 1

        # 3) Framework versions.
        for code, fw_key, label, src_key, status, is_default in FRAMEWORK_VERSIONS:
            defaults = {
                'framework': frameworks[fw_key],
                'version_label': label,
                'status': status,
                'is_default': is_default,
                'source_document': sources.get(src_key) if src_key else None,
            }
            _, created = FrameworkVersion.objects.update_or_create(code=code, defaults=defaults)
            stats['ver_created' if created else 'ver_updated'] += 1

        self.stdout.write(self.style.SUCCESS('Source Registry + Framework Versioning seeded.'))
        self.stdout.write(f"  created SourceDocuments: {stats['src_created']}")
        self.stdout.write(f"  updated SourceDocuments: {stats['src_updated']}")
        self.stdout.write(f"  created Frameworks (on demand): {stats['fw_created']}")
        self.stdout.write(f"  created FrameworkVersions: {stats['ver_created']}")
        self.stdout.write(f"  updated FrameworkVersions: {stats['ver_updated']}")
