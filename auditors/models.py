"""
Phase 4C — platform auditor onboarding + company-to-auditor assignment.

Additive. No payments, no marketplace pricing, no payouts, no chat, no external
share links. AuditorProfile does NOT make a user staff. Assigned auditors get
read-only context only; ControlAssessment updates remain staff-only.
"""
from django.db import models

from core.models import Company, User


class AuditorProfile(models.Model):
    STATUS_CHOICES = [
        ('pending_review', 'Pending Review'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='auditor_profile')
    full_name = models.CharField(max_length=160)
    organization_name = models.CharField(max_length=200, blank=True)
    license_or_membership_no = models.CharField(max_length=120, blank=True)
    specialization = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='SA')
    bio = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_review')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auditor_profiles'
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.status})"

    def is_active_auditor(self):
        return self.status == 'active'

    def is_listable(self):
        """Available for company assignment: active AND available."""
        return self.status == 'active' and self.is_available


class AuditorAssignment(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    SCOPE_CHOICES = [
        ('reports_only', 'Reports Only'),
        ('evidence_review', 'Evidence Review'),
        ('full_review', 'Full Review'),
    ]
    # Statuses that count as an "active" assignment (for duplicate prevention / access).
    ACTIVE_STATUSES = ('requested', 'accepted')

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='auditor_assignments')
    auditor = models.ForeignKey(AuditorProfile, on_delete=models.CASCADE, related_name='assignments')
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_assignments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='reports_only')
    notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auditor_assignments'
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.company.name} -> {self.auditor.full_name} ({self.status})"

    def is_active(self):
        return self.status in self.ACTIVE_STATUSES
