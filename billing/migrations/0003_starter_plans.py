"""Phase 8I-SUBSCRIPTION-A — seed 4 starter plans (idempotent, admin-editable).

Prices are safe PLACEHOLDERS in SAR; adjust in Django admin. No payment gateway,
no secrets. Reversible (removes only these plan codes).
"""
from decimal import Decimal

from django.db import migrations

STARTER_PLANS = [
    dict(code='trial', name='Trial', price_amount=Decimal('0'), billing_cycle='monthly',
         sort_order=0, auditor_review_enabled=False,
         max_evidence_files=20, max_pdf_exports=3, max_frameworks=1,
         description='Internal readiness tools trial. Not an official certification.'),
    dict(code='basic', name='Basic', price_amount=Decimal('499.00'), billing_cycle='monthly',
         sort_order=1, auditor_review_enabled=False,
         max_evidence_files=100, max_pdf_exports=10, max_frameworks=1,
         description='Internal readiness essentials for a single framework.'),
    dict(code='professional', name='Professional', price_amount=Decimal('1499.00'),
         billing_cycle='monthly', sort_order=2, auditor_review_enabled=True,
         max_evidence_files=1000, max_pdf_exports=50, max_frameworks=3,
         description='Internal readiness across multiple frameworks with auditor review.'),
    dict(code='enterprise', name='Enterprise', price_amount=Decimal('4999.00'),
         billing_cycle='monthly', sort_order=3, auditor_review_enabled=True,
         max_evidence_files=0, max_pdf_exports=0, max_frameworks=0,
         description='Unlimited internal readiness tooling and auditor review.'),
]


def create_plans(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    for p in STARTER_PLANS:
        Plan.objects.update_or_create(code=p['code'], defaults=p)


def remove_plans(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    Plan.objects.filter(code__in=[p['code'] for p in STARTER_PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [('billing', '0002_plan_companysubscription_activated_at_and_more')]
    operations = [migrations.RunPython(create_plans, remove_plans)]
