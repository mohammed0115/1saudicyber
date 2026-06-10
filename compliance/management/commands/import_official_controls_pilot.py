"""
Phase 2B — limited OFFICIAL pilot import (max 9 controls).

Proves the official-source import path end to end WITHOUT a full import. Control
text below was transcribed (short, control-statement only) from the official
public sources and is bound to a FrameworkVersion + SourceDocument seeded in
Phase 1:
  * NCA ECC 2:2024  -> Docs/SRS/NCA/ECC--2024-EN.pdf  (p.13, Public / TLP:White)
  * Aramco SACS-002 -> Docs/SRS/ARAMCO/sacs-002-third-party-cybersecurity-standard.pdf
  * SABIC CyberTrust -> Docs/SRS/SABIC/SABIC CyberTrust Standard v1-0.pdf (p.8)

Safety / scope:
  * idempotent (update_or_create keyed on framework + control_id).
  * NEVER touches CompanyControl or Evidence.
  * NEVER edits a legacy control: if a control with the same (framework,
    control_id) already exists WITHOUT a framework_version (i.e. a legacy
    334-Excel row), it is SKIPPED, not modified.
  * does NOT use the legacy 334 Excel as an authority.
  * requires Phase 1 seed: aborts (no random version creation) if a needed
    FrameworkVersion or its SourceDocument is missing.

Usage:
    python manage.py seed_framework_versions
    python manage.py import_official_controls_pilot
"""
from django.core.management.base import BaseCommand, CommandError

from compliance.models import (
    Framework, Domain, Control, FrameworkVersion, ControlVersion, ControlApplicabilityTag,
)

IMPORT_NOTE = 'Official limited pilot import (Phase 2B). Not a full import; for method proof only.'

# Each entry transcribes only the control statement from the official source.
PILOT = [
    # --- NCA ECC 2:2024 (framework NCA_ECC, version NCA-ECC-2-2024) ---
    dict(fw='NCA_ECC', fv='NCA-ECC-2-2024', control_id='1-1-1', ext='NCA ECC 1-1-1',
         domain_code='1', domain_name='Cybersecurity Governance', subdomain='1-1 Cybersecurity Strategy',
         title='Cybersecurity Strategy',
         statement=('The cybersecurity strategy of the entity shall be identified, documented and '
                    'approved, and supported by the Authorized Official; its goals shall align with '
                    'the relevant legislative and regulatory requirements.'),
         page=13, ref='NCA ECC 2:2024, 1- Cybersecurity Governance / 1-1 Cybersecurity Strategy', tags=[]),
    dict(fw='NCA_ECC', fv='NCA-ECC-2-2024', control_id='1-2-1', ext='NCA ECC 1-2-1',
         domain_code='1', domain_name='Cybersecurity Governance', subdomain='1-2 Cybersecurity Management',
         title='Cybersecurity Department',
         statement=('A dedicated cybersecurity department shall be established within the entity, '
                    'independent from the Information Technology and Communications Department.'),
         page=13, ref='NCA ECC 2:2024, 1- Cybersecurity Governance / 1-2 Cybersecurity Management', tags=[]),
    dict(fw='NCA_ECC', fv='NCA-ECC-2-2024', control_id='1-3-1', ext='NCA ECC 1-3-1',
         domain_code='1', domain_name='Cybersecurity Governance',
         subdomain='1-3 Cybersecurity Policies and Procedures',
         title='Cybersecurity Policies and Procedures',
         statement=('The cybersecurity department shall identify and document cybersecurity policies '
                    'and procedures, have them approved by the Authorized Official, and communicate '
                    'them to relevant personnel and parties.'),
         page=13, ref='NCA ECC 2:2024, 1- Cybersecurity Governance / 1-3 Policies and Procedures', tags=[]),

    # --- Aramco SACS-002 (framework ARAMCO_SACS002, version ARAMCO-SACS-002) ---
    dict(fw='ARAMCO_SACS002', fv='ARAMCO-SACS-002', control_id='TPC-1', ext='SACS-002 TPC-1',
         domain_code='GV', domain_name='Identify - Governance (GV)', subdomain='Governance (GV)',
         title='Cybersecurity Acceptable Use Policy (AUP)',
         statement=('The Third Party must establish, maintain and communicate a Cybersecurity '
                    'Acceptable Use Policy (AUP) governing the use of Third Party Technology Assets.'),
         page=None, ref='SACS-002 Third Party Cybersecurity Standard, IDENTIFY / Governance (GV), TPC-1',
         tags=[]),
    dict(fw='ARAMCO_SACS002', fv='ARAMCO-SACS-002', control_id='TPC-2', ext='SACS-002 TPC-2',
         domain_code='AC', domain_name='Protect - Access Control (AC)', subdomain='Access Control (AC)',
         title='Password Protection Measures',
         statement=('Password protection measures must be enforced by the Third Party (recommended: '
                    'min length 8 alphanumeric + special, history of last 12, max age 90 days, lockout '
                    'after 10 invalid attempts, screen auto-lock after 15 minutes).'),
         page=None, ref='SACS-002 Third Party Cybersecurity Standard, PROTECT / Access Control (AC), TPC-2',
         tags=[]),
    dict(fw='ARAMCO_SACS002', fv='ARAMCO-SACS-002', control_id='TPC-3', ext='SACS-002 TPC-3',
         domain_code='AC', domain_name='Protect - Access Control (AC)', subdomain='Access Control (AC)',
         title='Protection of Passwords and Authentication Codes',
         statement=('The Third Party must not write down, electronically store in clear text, or '
                    'disclose any password or authentication code used to access Assets or Critical '
                    'Facilities; this must be part of Third Party cybersecurity policies.'),
         page=None, ref='SACS-002 Third Party Cybersecurity Standard, PROTECT / Access Control (AC), TPC-3',
         tags=[]),

    # --- SABIC CyberTrust v1.0 (framework SABIC_CT, version SABIC-CYBERTRUST-1-0) ---
    dict(fw='SABIC_CT', fv='SABIC-CYBERTRUST-1-0', control_id='CT-01', ext='SABIC CT-01',
         domain_code='ISM', domain_name='Information Security Management',
         subdomain='Information security management',
         title='Information Security Policies',
         statement=('Suppliers must have defined information security policies, approved by their '
                    'management and communicated to people with access to their information systems.'),
         page=8, ref='SABIC CyberTrust Standard v1.0, Information Security Management, CT-01', tags=[]),
    dict(fw='SABIC_CT', fv='SABIC-CYBERTRUST-1-0', control_id='CT-02', ext='SABIC CT-02',
         domain_code='ID.IM', domain_name='Identify - Improvement (ID.IM)', subdomain='Improvement (ID.IM)',
         title='Self-Assessments',
         statement=('Suppliers must perform at least a yearly self-assessment of their operational '
                    'resilience and cybersecurity practices covering all requirements of the standard '
                    '(or when requested by SABIC).'),
         page=8, ref='SABIC CyberTrust Standard v1.0, IDENTIFY / Improvement (ID.IM), CT-02', tags=[]),
    dict(fw='SABIC_CT', fv='SABIC-CYBERTRUST-1-0', control_id='CT-03', ext='SABIC CT-03',
         domain_code='ID.AM', domain_name='Identify - Asset Management (ID.AM)',
         subdomain='Asset Management (ID.AM)',
         title='Asset Management',
         statement=('SABIC Assets associated with information processing facilities managed by the '
                    'Supplier must be identified, and an inventory of these Assets must be drawn up '
                    'and maintained by the Supplier.'),
         page=8, ref='SABIC CyberTrust Standard v1.0, IDENTIFY / Asset Management (ID.AM), CT-03', tags=[]),
]


class Command(BaseCommand):
    help = 'Phase 2B: limited official pilot import (<=9 controls), idempotent and non-destructive.'

    def handle(self, *args, **options):
        stats = dict(created=0, updated=0, versions=0, tags=0)

        # Resolve framework versions up front; never invent a version.
        needed_fvs = {e['fv'] for e in PILOT}
        versions = {fv.code: fv for fv in FrameworkVersion.objects.filter(code__in=needed_fvs)}
        missing = needed_fvs - set(versions)
        if missing:
            raise CommandError(
                f"Missing FrameworkVersion(s): {sorted(missing)}. "
                f"Run `python manage.py seed_framework_versions` first.")
        for code, fv in versions.items():
            if fv.source_document is None:
                raise CommandError(
                    f"FrameworkVersion {code} has no source_document. Re-run seed_framework_versions.")

        for e in PILOT:
            fv = versions[e['fv']]
            src = fv.source_document
            fw = fv.framework
            domain, _ = Domain.objects.get_or_create(
                framework=fw, code=e['domain_code'], defaults={'name': e['domain_name']})

            # Phase 2D: official identity is (framework_version, control_id). A legacy
            # row with the same (framework, control_id) but framework_version=NULL is a
            # DIFFERENT identity and is left completely untouched — they coexist.
            control, created = Control.objects.update_or_create(
                framework_version=fv, control_id=e['control_id'],
                defaults=dict(
                    framework=fw, domain=domain, title=e['title'], description=e['statement'],
                    source_document=src,
                    source_page=e['page'], source_reference=e['ref'],
                    external_reference=e['ext'], is_legacy_import=False,
                    import_notes=IMPORT_NOTE, priority='high',
                ))
            stats['created' if created else 'updated'] += 1

            ControlVersion.objects.update_or_create(
                control=control, framework_version=fv, version_label=fv.version_label or fv.code,
                defaults=dict(
                    source_document=src, control_id_snapshot=e['control_id'],
                    title_snapshot=e['title'], statement_snapshot=e['statement'],
                    change_summary='Initial official pilot import.'))
            stats['versions'] += 1

            for tag in e['tags']:
                _, tcreated = ControlApplicabilityTag.objects.get_or_create(
                    control=control, tag=tag, defaults={'source': 'official'})
                stats['tags'] += int(tcreated)

        self.stdout.write(self.style.SUCCESS('Official pilot import complete (limited).'))
        self.stdout.write(f"  created official controls: {stats['created']}")
        self.stdout.write(f"  updated official controls: {stats['updated']}")
        self.stdout.write(f"  control versions written: {stats['versions']}")
        self.stdout.write(f"  applicability tags created: {stats['tags']}")
        self.stdout.write("  legacy controls: untouched (coexist via framework_version identity)")
