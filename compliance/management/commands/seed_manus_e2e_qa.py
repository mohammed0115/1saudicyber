"""QA-only seeder for Manus E2E auditor-verdict testing (Phase 8D-2-FIX-B).

Prepares a self-contained, idempotent QA scenario so a tester can exercise the
full *activated auditor -> assigned company file -> final verdict* workflow:

  - one company test account (User + Company, QA-marked, active subscription)
  - one activated auditor test account (User + AuditorProfile status='active')
  - an ACCEPTED assignment linking the auditor to the company file
  - one control plan + evidence checklist + evidence submission (with advisory
    AI + rule-engine context) ready for an auditor final verdict

Safety:
  * QA-ONLY. Never runs automatically; must be invoked explicitly and confirmed
    with --confirm (or DJANGO_ALLOW_QA_SEED=1).
  * Idempotent — re-running updates the same QA fixtures, never duplicates.
  * Uses obviously-fake QA data only (no real customer data).
  * Creates NO payment/invoice records (manual subscription activation only).
  * Does NOT issue any final compliance decision or certificate by itself.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

# Obviously-fake, namespaced QA identities so they are easy to spot and purge.
QA_COMPANY_CR = 'QA-MANUS-0001'
QA_COMPANY_USER_EMAIL = 'qa.company@manus-e2e.test'
QA_AUDITOR_EMAIL = 'qa.auditor@manus-e2e.test'
QA_PASSWORD = 'ManusQA-pass-12345'
QA_PLAN_NAME = 'QA/TEST — Manus E2E (not a real subscription)'
QA_FV_CODE = 'ARAMCO-SACS-002'
QA_FRAMEWORK_CODE = 'ARAMCO_SACS002'


class Command(BaseCommand):
    help = ('QA-ONLY: seed an activated auditor + assigned company file + evidence '
            'submission for Manus auditor-verdict E2E testing. Idempotent. '
            'Requires --confirm (or DJANGO_ALLOW_QA_SEED=1).')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Required acknowledgement that this seeds QA-only data.')

    def handle(self, *args, **opts):
        if not (opts.get('confirm') or os.environ.get('DJANGO_ALLOW_QA_SEED') == '1'):
            raise CommandError(
                'Refusing to run without acknowledgement. This command seeds QA-ONLY '
                'test data. Re-run with --confirm (or set DJANGO_ALLOW_QA_SEED=1).')

        with transaction.atomic():
            company, company_user = self._company_and_user()
            auditor_user, auditor_profile = self._activated_auditor()
            assignment = self._accepted_assignment(company, auditor_profile, company_user)
            submission = self._company_file_with_evidence(company)

        self.stdout.write(self.style.SUCCESS('Manus E2E QA data ready (idempotent).'))
        self.stdout.write('')
        self.stdout.write('  Company account     : %s / %s' % (QA_COMPANY_USER_EMAIL, QA_PASSWORD))
        self.stdout.write('  Activated auditor   : %s / %s' % (QA_AUDITOR_EMAIL, QA_PASSWORD))
        self.stdout.write('  Company             : %s (CR %s)' % (company.name, company.cr_number))
        self.stdout.write('  Assignment          : id=%s status=%s' % (assignment.id, assignment.status))
        if submission is not None:
            from django.urls import reverse
            self.stdout.write('  Evidence submission : id=%s (ready for auditor verdict)' % submission.id)
            self.stdout.write('  Verdict URL         : %s'
                              % reverse('compliance:auditor_verdict', args=[submission.id]))
        else:
            self.stdout.write(self.style.WARNING(
                '  Evidence submission : SKIPPED — official controls for %s are not '
                'imported in this environment. The auditor + assignment are still '
                'usable; import official controls to enable verdict QA.' % QA_FV_CODE))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'QA-ONLY data. Do not use in production. No payment record was created.'))

    # ---------- builders (each idempotent) ----------
    def _company_and_user(self):
        from core.models import Company, User
        from billing.subscription_access import activate_company_subscription
        company, _ = Company.objects.update_or_create(
            cr_number=QA_COMPANY_CR,
            defaults=dict(name='QA Manus E2E Co (TEST)', name_ar='شركة اختبار مانوس (تجريبي)',
                          sector='oil_gas', size='small', contact_email='qa.company@manus-e2e.test'))
        user, _ = User.objects.update_or_create(
            email=QA_COMPANY_USER_EMAIL,
            defaults=dict(username=QA_COMPANY_USER_EMAIL, role='company_admin',
                          company=company, first_name='QA', last_name='Company'))
        user.set_password(QA_PASSWORD)
        user.save()
        # Manual QA activation — no payment is taken (see activate_company_subscription).
        activate_company_subscription(company, QA_PLAN_NAME, days=30)
        return company, user

    def _activated_auditor(self):
        from core.models import User
        from auditors.models import AuditorProfile
        user, _ = User.objects.update_or_create(
            email=QA_AUDITOR_EMAIL,
            defaults=dict(username=QA_AUDITOR_EMAIL, role='auditor',
                          first_name='QA', last_name='Auditor'))
        user.set_password(QA_PASSWORD)
        user.save()
        profile, _ = AuditorProfile.objects.update_or_create(
            user=user,
            defaults=dict(full_name='QA Manus Auditor (TEST)', organization_name='QA Org',
                          status='active', is_available=True))
        return user, profile

    def _accepted_assignment(self, company, auditor_profile, requested_by):
        from auditors.models import AuditorAssignment
        assignment, _ = AuditorAssignment.objects.update_or_create(
            company=company, auditor=auditor_profile,
            defaults=dict(status='accepted', scope='reports_only', requested_by=requested_by))
        return assignment

    def _company_file_with_evidence(self, company):
        """Build an official control plan + checklist + one evidence submission with
        advisory AI + rule context, ready for an auditor final verdict. Returns the
        submission, or None if official controls are unavailable in this environment.
        """
        from compliance.models import (FrameworkVersion, Control, CompanyFrameworkScope,
                                        EvidenceChecklistItem, EvidenceSubmission)
        from compliance.framework_applicability import evaluate_company
        from compliance.framework_scope import (propose_framework_scopes,
                                                 approve_framework_scope,
                                                 generate_control_applicability_plan)
        from compliance.evidence_planning import (generate_evidence_requirements,
                                                  generate_evidence_checklist_for_company)

        fv = FrameworkVersion.objects.filter(code=QA_FV_CODE).first()
        if fv is None or not Control.objects.filter(
                framework_version=fv, is_legacy_import=False).exists():
            return None  # official controls not imported here — auditor/assignment still usable.

        # Make the QA company indicate an Aramco relationship so the scope applies.
        from compliance.models import CompanyIntakeProfile
        CompanyIntakeProfile.objects.update_or_create(
            company=company, defaults=dict(works_with_aramco=True, review_status='completed'))

        evaluate_company(company, apply=True)
        propose_framework_scopes(company, apply=True)
        scope = CompanyFrameworkScope.objects.filter(company=company, framework_version=fv).first()
        if scope is None:
            return None
        if scope.status != 'approved':
            approve_framework_scope(scope)
        generate_control_applicability_plan(company, scope, apply=True)
        generate_evidence_requirements(apply=True, framework_version_code=QA_FV_CODE)
        generate_evidence_checklist_for_company(company, apply=True)

        item = EvidenceChecklistItem.objects.filter(company=company).first()
        if item is None:
            return None

        sub = EvidenceSubmission.objects.filter(
            company=company, checklist_item=item,
            original_filename='qa-policy.txt').order_by('id').first()
        if sub is None:
            sub = EvidenceSubmission.objects.create(
                company=company, checklist_item=item,
                uploaded_file=SimpleUploadedFile(
                    'qa-policy.txt', b'QA TEST: access control policy approved by management.',
                    content_type='text/plain'),
                original_filename='qa-policy.txt', file_type='txt', file_size=58)

        # Build advisory context (extraction + AI + rule) so the verdict screen is complete.
        try:
            from compliance.evidence_extraction import save_extraction_for_submission
            from compliance.rule_engine import evaluate_submission_rules
            save_extraction_for_submission(sub)
            evaluate_submission_rules(sub)
        except Exception:
            # Context is a convenience for QA; never block seeding on it.
            pass
        return sub
