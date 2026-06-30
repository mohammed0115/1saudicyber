"""
Core Models - User and Company Registration
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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
    mfa_secret = models.CharField(max_length=64, blank=True)

    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


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
        ('certified', 'Certified'),
        ('expired', 'Certificate Expired'),
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

    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return f"{self.name} ({self.cr_number})"

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

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        who = self.user.email if self.user else 'anonymous'
        return f"{who} {self.method} {self.path} [{self.status_code}]"
