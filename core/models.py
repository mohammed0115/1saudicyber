"""
Core Models - User and Company Registration
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q


class CustomUserManager(BaseUserManager):
    """Custom user manager that uses email as the unique identifier."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model with role-based access."""
    ROLE_CHOICES = [
        ('admin', 'Platform Admin'),
        ('company_admin', 'Company Admin'),
        ('compliance_officer', 'Compliance Officer'),
        ('it_security', 'IT/Security Team'),
        ('bu_manager', 'Business Unit Manager'),
        ('executive', 'Executive'),
        ('auditor', 'Certified Auditor'),
    ]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='company_admin')
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    phone = models.CharField(max_length=20, blank=True)
    preferred_language = models.CharField(max_length=2, choices=[('ar', 'Arabic'), ('en', 'English')], default='ar')

    # Email verification (FR-002.8)
    email_verified = models.BooleanField(default=False)
    # Multi-factor authentication (FR-012.3 / NFR-013)
    mfa_enabled = models.BooleanField(default=False)
    # TOTP secret, encrypted at rest (DD P1). Widened to hold the Fernet ciphertext; never
    # read/write this field directly — use get_mfa_secret()/set_mfa_secret().
    mfa_secret = models.CharField(max_length=255, blank=True)

    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def set_mfa_secret(self, plain):
        """Store the TOTP secret encrypted at rest. Caller still saves the instance."""
        from core.crypto import encrypt_secret
        self.mfa_secret = encrypt_secret(plain)

    def get_mfa_secret(self):
        """Return the plaintext TOTP secret (decrypts ciphertext; passes legacy plaintext)."""
        from core.crypto import decrypt_secret
        return decrypt_secret(self.mfa_secret)


class CompanyMembership(models.Model):
    """Explicit, auditable membership of a user in a company tenant.

    ``User.company`` remains a compatibility pointer for legacy code. New tenant
    resolution uses active memberships, which allows one account to work with
    more than one company without weakening the tenant boundary.
    """
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='company_memberships')
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=User.ROLE_CHOICES, default='compliance_officer')
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'company_memberships'
        constraints = [
            models.UniqueConstraint(fields=['user', 'company'], name='company_membership_unique'),
            models.UniqueConstraint(
                fields=['user'], condition=Q(is_active=True, is_default=True),
                name='company_membership_one_active_default',
            ),
        ]
        indexes = [models.Index(fields=['company', 'is_active'])]

    def __str__(self):
        return f'{self.user_id}@{self.company_id} ({self.role})'


class CompanyDeletionProtected(Exception):
    """Raised when application code tries to hard-delete a Company that owns a final audit
    record (an issued AuditReport) — those records must be retained, not silently cascaded away."""


def _company_has_issued_report(company_pks):
    """True if any of the given companies owns an issued AuditReport (via its assessments)."""
    from django.apps import apps
    AuditReport = apps.get_model('auditor_portal', 'AuditReport')
    return AuditReport.objects.filter(assessment__company__in=list(company_pks)).exists()


class CompanyQuerySet(models.QuerySet):
    """P0-02: block bulk/QuerySet deletion (and Django admin bulk delete, which routes through
    delete_queryset -> QuerySet.delete) when ANY company in the set owns an issued report. This
    is the backstop the per-instance Company.delete() cannot provide, since QuerySet.delete()
    and the cascade collector bypass the model method."""
    def delete(self):
        if _company_has_issued_report(self.values_list('pk', flat=True)):
            raise CompanyDeletionProtected(
                'Cannot delete a company that owns an issued audit report. Archive it instead.')
        return super().delete()


class Company(models.Model):
    """Registered company seeking compliance certification."""
    SECTOR_CHOICES = [
        ('oil_gas', 'Oil & Gas'),
        ('petrochemical', 'Petrochemical'),
        ('banking', 'Banking & Finance'),
        ('telecom', 'Telecommunications'),
        ('healthcare', 'Healthcare'),
        ('government', 'Government'),
        ('defense', 'Defense'),
        ('energy', 'Energy & Utilities'),
        ('manufacturing', 'Manufacturing'),
        ('technology', 'Technology'),
        ('logistics', 'Logistics & Transport'),
        ('construction', 'Construction'),
        ('retail', 'Retail'),
        ('education', 'Education'),
        ('other', 'Other'),
    ]

    SIZE_CHOICES = [
        ('micro', 'Micro (1-9 employees)'),
        ('small', 'Small (10-49 employees)'),
        ('medium', 'Medium (50-249 employees)'),
        ('large', 'Large (250-999 employees)'),
        ('enterprise', 'Enterprise (1000+ employees)'),
    ]

    STATUS_CHOICES = [
        ('registered', 'Registered'),
        ('classified', 'Classified'),
        ('in_assessment', 'In Assessment'),
        ('audit_ready', 'Audit Ready'),
        # Cyber-5 provides readiness tooling and internal reviews; it never
        # represents an official external certification.
        ('review_ready', 'Ready for Internal Review'),
        ('expired', 'Review Expired'),
    ]

    name = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255, blank=True)
    cr_number = models.CharField(max_length=20, unique=True, verbose_name='CR Number')
    sector = models.CharField(max_length=30, choices=SECTOR_CHOICES)
    size = models.CharField(max_length=20, choices=SIZE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='registered')

    target_aramco = models.BooleanField(default=False)
    target_sabic = models.BooleanField(default=False)
    target_nca = models.BooleanField(default=False)

    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='SA')
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)

    # Phase 4A — self-service onboarding state (additive, defaults preserve old rows).
    onboarding_completed = models.BooleanField(default=False)

    risk_level = models.CharField(max_length=20, blank=True, choices=[
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical'),
    ])
    classification_date = models.DateTimeField(null=True, blank=True)
    classification_summary = models.TextField(blank=True)
    classification_summary_ar = models.TextField(blank=True)

    overall_compliance_score = models.FloatField(default=0.0)
    nca_score = models.FloatField(default=0.0)
    aramco_score = models.FloatField(default=0.0)
    sabic_score = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return f"{self.name} ({self.cr_number})"

    def delete(self, *args, **kwargs):
        """P0-02: an ordinary application delete (self-service PDPL view, admin single delete)
        is refused when this company owns an issued audit report — deleting it would cascade the
        final report away. Retain/archive instead. (A DBA acting directly on the DB is out of
        scope; every application path is covered by this + CompanyQuerySet.delete().)"""
        if _company_has_issued_report([self.pk]):
            raise CompanyDeletionProtected(
                'Cannot delete a company that owns an issued audit report. Archive it instead.')
        return super().delete(*args, **kwargs)

    @property
    def country_display(self):
        """UAT-10: human label for the Arabic UI while keeping the code ('SA') stored."""
        if (self.country or '').strip().upper() in ('SA', 'KSA'):
            return 'المملكة العربية السعودية'
        return self.country or '—'

    @property
    def applicable_frameworks(self):
        frameworks = []
        if self.target_nca:
            frameworks.append('NCA ECC')
        if self.target_aramco:
            frameworks.append('Aramco SACS-002')
        if self.target_sabic:
            frameworks.append('SABIC CyberTrust')
        return frameworks


class CompanyJourney(models.Model):
    """Single persisted source for the company-facing readiness journey.

    Product screens use this state instead of inferring a journey from unrelated
    status fields. Transitions are intentionally product-neutral and do not
    imply a regulator-issued certificate.
    """
    STATE_CHOICES = [
        ('registered', 'Registered'),
        ('subscription_pending', 'Subscription Pending'),
        ('intake_in_progress', 'Intake In Progress'),
        ('scope_ready', 'Framework Scope Ready'),
        ('evidence_in_progress', 'Evidence In Progress'),
        ('review_ready', 'Ready for Internal Review'),
        ('under_internal_review', 'Under Internal Review'),
        ('review_closed', 'Internal Review Closed'),
    ]
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='journey')
    state = models.CharField(max_length=32, choices=STATE_CHOICES, default='registered')
    state_reason = models.CharField(max_length=250, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_journeys'
        indexes = [models.Index(fields=['state', 'updated_at'])]

    def __str__(self):
        return f'{self.company_id}: {self.state}'


class EmailVerificationToken(models.Model):
    """One-time token emailed to a user to verify their address (FR-002.8)."""
    import uuid as _uuid
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='verification_tokens')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'email_verification_tokens'

    @staticmethod
    def generate():
        import secrets
        return secrets.token_urlsafe(32)


class EmailOTP(models.Model):
    """Phase 8D-3B-AUTH-A — 6-digit email-verification OTP (hashed, expiring).

    The raw 6-digit code is NEVER stored: only a salted hash (Django password
    hasher) is kept. Each OTP expires after a short TTL and allows a limited
    number of attempts; an expired or over-attempted OTP can never verify.
    """
    PURPOSE_CHOICES = [('email_verify', 'Email Verification')]

    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='email_otps')
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES, default='email_verify')
    code_hash = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'email_otps'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'purpose', 'used'])]

    def __str__(self):
        return f"OTP({self.user_id}, {self.purpose}, used={self.used})"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at


class AuditLogQuerySet(models.QuerySet):
    """Application-facing audit logs are immutable after insertion."""
    def delete(self):
        raise RuntimeError('AuditLog is append-only; use the retention service.')


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    def purge_before(self, when):
        """Retention-only hard delete, intentionally not exposed as QuerySet.delete()."""
        return self.get_queryset().filter(created_at__lt=when)._raw_delete(self.db)


class AuditLog(models.Model):
    """General system audit trail for all user actions (FR-012.8 / NFR-021 / NFR-046)."""
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries')
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries')
    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=300, blank=True)
    action = models.CharField(max_length=100, blank=True)
    status_code = models.IntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', '-created_at'])]   # DD: per-tenant audit trail

    def __str__(self):
        who = self.user.email if self.user else 'anonymous'
        return f"{who} {self.method} {self.path} [{self.status_code}]"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError('AuditLog is append-only and cannot be updated.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError('AuditLog is append-only; use the retention service.')


class UserInvite(models.Model):
    """DD-fix (commercial) — invite a teammate to a company with a role.

    A company_admin/admin invites an email; an accept link (token) lets the invitee set a
    password and join that company with the chosen role. Tenant-scoped: the invite carries
    the inviter's company, so acceptance can never join a different tenant.
    """
    STATUS_CHOICES = [('pending', 'Pending'), ('accepted', 'Accepted'), ('cancelled', 'Cancelled')]

    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=User.ROLE_CHOICES, default='compliance_officer')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='sent_invites')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'user_invites'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', 'status'])]

    def is_valid(self):
        from django.utils import timezone
        return self.status == 'pending' and self.expires_at > timezone.now()


class Notification(models.Model):
    """In-app notification for any user (company, auditor, or platform admin).

    Complements the existing email side-effects with a persistent, in-app inbox +
    unread badge. Created via core.notify_services.notify(...). Read-only history;
    never carries a compliance decision.
    """
    KIND_CHOICES = [
        ('rfi', 'RFI'), ('finding', 'Finding'), ('assignment', 'Assignment'),
        ('verdict', 'Verdict'), ('message', 'Message'), ('payment', 'Payment'),
        ('report', 'Report'), ('system', 'System'),
    ]
    recipient = models.ForeignKey('User', on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='system')
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True)  # relative link to the related item
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'is_read'])]

    def __str__(self):
        return f"{self.recipient_id}: {self.title[:40]}"
