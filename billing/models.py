"""
Phase 4B — subscription access control (foundation only).
Phase 8I-SUBSCRIPTION-A — Plan + Payment foundation (internal, Moyasar-ready).

NO payment gateway CALLS, NO card data, NO external secrets in this phase. The
models record subscription STATE and (placeholder) payment records so report
viewing/exports can be gated and so a later phase can connect Moyasar safely.
Activation remains manual (admin / service layer / management command).
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import Company, User


class Plan(models.Model):
    """Phase 8I — a subscription plan (admin-editable; prices are placeholders)."""
    BILLING_CYCLE_CHOICES = [('monthly', 'Monthly'), ('yearly', 'Yearly')]

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    currency = models.CharField(max_length=8, default='SAR')
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES, default='monthly')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    # Feature flags (internal readiness tools only — never an official certification).
    evidence_upload_enabled = models.BooleanField(default=True)
    gap_analysis_enabled = models.BooleanField(default=True)
    risk_engine_enabled = models.BooleanField(default=True)
    commercial_reports_enabled = models.BooleanField(default=True)
    pdf_export_enabled = models.BooleanField(default=True)
    auditor_review_enabled = models.BooleanField(default=False)

    # Limits (0 = unlimited).
    max_companies = models.PositiveIntegerField(default=1)
    max_evidence_files = models.PositiveIntegerField(default=0)
    max_pdf_exports = models.PositiveIntegerField(default=0)
    max_frameworks = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    FEATURE_FLAGS = ('evidence_upload_enabled', 'gap_analysis_enabled', 'risk_engine_enabled',
                     'commercial_reports_enabled', 'pdf_export_enabled', 'auditor_review_enabled')
    LIMIT_FIELDS = ('max_companies', 'max_evidence_files', 'max_pdf_exports', 'max_frameworks')

    class Meta:
        db_table = 'billing_plans'
        ordering = ['sort_order', 'price_amount']

    def __str__(self):
        return f"{self.name} ({self.code})"


class CompanySubscription(models.Model):
    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('trial', 'Trial'),
        ('pending_payment', 'Pending Payment'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]
    PROVIDER_CHOICES = [('manual', 'Manual'), ('moyasar', 'Moyasar')]
    # Statuses that count as "active" before the date check.
    ACTIVE_STATUSES = ('active', 'trial')

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    plan_name = models.CharField(max_length=120, blank=True)
    plan = models.ForeignKey('billing.Plan', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='subscriptions')
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activated_subscriptions')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_subscriptions')
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_subscriptions')
    # Moyasar-readiness placeholders (no API calls, no secrets in this phase).
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='manual')
    provider_subscription_id = models.CharField(max_length=128, blank=True)
    # Fine-grained capability flags (default permissive once active).
    report_exports_allowed = models.BooleanField(default=True)
    auditor_assignment_allowed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_subscriptions'
        ordering = ['company']

    def __str__(self):
        return f"{self.company.name} :: {self.status}"

    def is_active(self):
        """True only if status is active/trial AND not past ends_at."""
        if self.status not in self.ACTIVE_STATUSES:
            return False
        return self.ends_at is None or self.ends_at >= timezone.now()


class Payment(models.Model):
    """Phase 8I — a payment record (manual now; Moyasar-ready fields, no API calls)."""
    PROVIDER_CHOICES = [('manual', 'Manual'), ('moyasar', 'Moyasar')]
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'),
        ('cancelled', 'Cancelled'), ('refunded', 'Refunded'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payments')
    subscription = models.ForeignKey('billing.CompanySubscription', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='payments')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='manual')
    provider_payment_id = models.CharField(max_length=128, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    currency = models.CharField(max_length=8, default='SAR')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference = models.CharField(max_length=160, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_payments')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_payments'
        ordering = ['-created_at']
        constraints = [
            # DD-fix (DB integrity): money can never be negative.
            models.CheckConstraint(condition=models.Q(amount__gte=0), name='payment_amount_non_negative'),
        ]

    def __str__(self):
        return f"{self.company_id}:{self.amount} {self.currency} ({self.status})"


class PaymentEvent(models.Model):
    """Append-only provider event inbox used for idempotent payment processing."""
    PROVIDER_CHOICES = Payment.PROVIDER_CHOICES
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='payment_events')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='provider_events')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    signature_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_events'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'provider_event_id'],
                                    name='payment_event_provider_event_unique'),
        ]
        indexes = [models.Index(fields=['payment', 'created_at'])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError('PaymentEvent is append-only and cannot be updated.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError('PaymentEvent is append-only and cannot be deleted.')


class PaymentEventProcessing(models.Model):
    """Mutable processing projection for an immutable provider event."""
    STATUS_CHOICES = [
        ('received', 'Received'), ('processing', 'Processing'), ('completed', 'Completed'),
        ('deferred', 'Deferred'), ('failed', 'Failed'),
    ]
    event = models.OneToOneField(PaymentEvent, on_delete=models.CASCADE, related_name='processing')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_event_processing'
        indexes = [models.Index(fields=['status', 'updated_at'])]
