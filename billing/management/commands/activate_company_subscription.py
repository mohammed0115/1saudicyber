"""Manually activate a company's subscription (no payment provider)."""
from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from billing.subscription_access import activate_company_subscription


class Command(BaseCommand):
    help = 'Activate (or extend) a company subscription manually. No payment is taken.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--plan-name', type=str, default='UAT Plan')
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **opts):
        company = Company.objects.filter(id=opts['company_id']).first()
        if company is None:
            raise CommandError(f"No company with id={opts['company_id']}.")
        sub = activate_company_subscription(
            company, plan_name=opts['plan_name'], days=opts['days'])
        self.stdout.write(self.style.SUCCESS(
            f"Subscription for '{company.name}' set to {sub.status} "
            f"(plan={sub.plan_name}, ends_at={sub.ends_at})."))
