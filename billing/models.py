"""
Phase 4B — subscription access control (foundation only).

NO payment gateway, NO card data, NO external provider. This model records a
company's subscription STATUS so report viewing/exports can be gated. Activation
is manual (Django admin or the activate_company_subscription management command).
"""
from django.db import models
from django.utils import timezone

from core.models import Company, User


class CompanySubscription(models.Model):
    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]
    # Statuses that count as "active" before the date check.
    ACTIVE_STATUSES = ('active', 'trial')

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    plan_name = models.CharField(max_length=120, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activated_subscriptions')
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
