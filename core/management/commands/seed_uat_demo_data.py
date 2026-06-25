"""
Phase 4E — safe UAT/demo sample-data seeder. LOCAL UAT ONLY.

Dry-run by default (writes nothing). With --apply it creates a sample company,
a minimal intake profile, demo users (company / staff / auditor), and optionally
an active demo subscription. It NEVER imports official controls, never imports
OTCC/DCC, never creates CompanyControl, and never fabricates compliance
decisions (no ControlAssessment). Idempotent (keyed by CR number / email).

Passwords come from the UAT_DEMO_PASSWORD env var. If it is missing in --apply
mode, a clearly-temporary LOCAL-ONLY default is used and a warning is printed
(the value is a placeholder, not a secret).
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Company, User

SAMPLE_CR = '1010123456'
COMPANY_USER_EMAIL = 'client@1saudicyber.local'
STAFF_USER_EMAIL = 'admin@1saudicyber.local'
AUDITOR_USER_EMAIL = 'auditor@1saudicyber.local'
LOCAL_ONLY_DEFAULT_PASSWORD = 'uat-demo-local-only-change-me'  # placeholder, not a secret


class Command(BaseCommand):
    help = ('Create safe UAT/demo sample data (LOCAL UAT ONLY). Dry-run by default; '
            'use --apply to write. Never imports official controls/OTCC/DCC, never '
            'creates CompanyControl, never fabricates ControlAssessment.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write the demo data.')
        parser.add_argument('--dry-run', action='store_true', help='Explicit dry-run (default).')
        parser.add_argument('--subscribe', action='store_true',
                            help='Also activate a 30-day demo subscription for the sample company.')

    def handle(self, *args, **opts):
        apply = opts['apply'] and not opts['dry_run']
        items = [
            f"Company  : Najd Digital Solutions LLC (CR {SAMPLE_CR})",
            "Intake   : minimal demo intake profile (review_status=completed)",
            f"User     : {COMPANY_USER_EMAIL} (company_admin)",
            f"User     : {STAFF_USER_EMAIL} (staff)",
            f"User     : {AUDITOR_USER_EMAIL} (auditor) + active AuditorProfile",
        ]
        if opts['subscribe']:
            items.append("Billing  : active demo subscription (30 days)")

        if not apply:
            self.stdout.write("DRY-RUN (no data written). Would create:")
            for it in items:
                self.stdout.write(f"  - {it}")
            self.stdout.write("Run again with --apply to create the demo data.")
            return

        password = os.getenv('UAT_DEMO_PASSWORD')
        if not password:
            password = LOCAL_ONLY_DEFAULT_PASSWORD
            self.stdout.write(self.style.WARNING(
                "UAT_DEMO_PASSWORD not set; using a temporary LOCAL-ONLY default password. "
                "Do NOT use in production."))

        with transaction.atomic():
            company, _ = Company.objects.get_or_create(
                cr_number=SAMPLE_CR,
                defaults=dict(
                    name='Najd Digital Solutions LLC', name_ar='شركة نجد للحلول الرقمية',
                    sector='technology', size='medium', city='Riyadh', country='SA',
                    description='UAT demo company — do not use in production.',
                    website='https://example.local', contact_email=COMPANY_USER_EMAIL,
                    contact_phone='+966500000001',
                    target_nca=True, target_aramco=True, target_sabic=True,
                    onboarding_completed=True))

            from compliance.models import CompanyIntakeProfile
            CompanyIntakeProfile.objects.get_or_create(
                company=company,
                defaults=dict(
                    sector='technology', is_critical_system_operator=True,
                    uses_cloud_services=True, provides_cloud_services=True,
                    handles_sensitive_data=True, handles_personal_data=True,
                    has_remote_work=True, manages_official_social_media_accounts=True,
                    works_with_aramco=True, works_with_sabic=True, review_status='completed'))

            self._user(COMPANY_USER_EMAIL, password, company=company,
                       role='company_admin', first_name='Ahmed', last_name='Al-Qahtani')
            self._user(STAFF_USER_EMAIL, password, role='admin', is_staff=True,
                       first_name='UAT', last_name='Staff')
            auditor_user = self._user(AUDITOR_USER_EMAIL, password, role='auditor',
                                      first_name='UAT', last_name='Auditor')

            from auditors.models import AuditorProfile
            AuditorProfile.objects.get_or_create(
                user=auditor_user,
                defaults=dict(full_name='UAT Auditor', organization_name='1SaudiCyber UAT',
                              specialization='NCA / Aramco / SABIC', city='Riyadh',
                              status='active', is_available=True))

            if opts['subscribe']:
                from billing.subscription_access import activate_company_subscription
                activate_company_subscription(company, 'UAT Demo Plan', days=30)

        self.stdout.write(self.style.SUCCESS(
            "UAT demo data ready (LOCAL UAT ONLY). No official controls / OTCC / DCC / "
            "CompanyControl / ControlAssessment were created."))

    def _user(self, email, password, **extra):
        user = User.objects.filter(email=email).first()
        if user:
            return user
        return User.objects.create_user(username=email, email=email, password=password, **extra)
